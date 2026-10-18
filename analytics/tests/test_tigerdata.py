import copy
import importlib.util
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from analytics.tigerdata.__main__ import import_once, main
from analytics.tigerdata.database import Database, DatabaseError
from analytics.tigerdata.source import ROOT, InputError, discover, prepare, records


class Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self):
        self.sessions = {}
        self.checkpoints = {}
        self.rows = {name: [] for name in ('frames', 'events', 'round_metrics', 'trend_snapshots')}
        self.trend_imports = {}
        self.refreshes = 0
        self.fail_refresh = False
        self.fail_table = None
        self.rollbacks = 0

    @contextmanager
    def transaction(self):
        snapshot = copy.deepcopy((self.sessions, self.checkpoints, self.rows, self.trend_imports))
        try:
            yield
        except Exception:
            self.sessions, self.checkpoints, self.rows, self.trend_imports = snapshot
            self.rollbacks += 1
            raise

    def execute(self, query, params=None):
        text = query.as_string() if hasattr(query, 'as_string') else query
        if text.startswith('INSERT INTO') and '"sessions"' in text:
            self.sessions[params[0]] = params[2].obj
        elif text.startswith('SELECT fingerprint'):
            value = self.checkpoints.get(tuple(params))
            return Result((value,) if value else None)
        elif text.startswith('INSERT INTO') and '"ingest_rounds"' in text:
            self.checkpoints[tuple(params[:2])] = params[2]
        elif text.startswith('SELECT signature'):
            return Result(self.trend_imports.get(params[0]))
        elif text.startswith('INSERT INTO') and '"trend_imports"' in text:
            self.trend_imports[params[0]] = (params[1], False, params[3], params[4])
        elif text.startswith('UPDATE') and '"trend_imports"' in text:
            signature, ready, first, last = self.trend_imports[params[0]]
            self.trend_imports[params[0]] = (signature, True, first, last)
        elif text.startswith('CALL refresh'):
            if self.fail_refresh:
                raise RuntimeError('private driver message')
            self.refreshes += 1
        elif text.startswith('DELETE'):
            table = next(name for name in self.rows if f'"{name}"' in text)
            self.rows[table] = [row for row in self.rows[table] if tuple(row[1:1 + len(params)]) != tuple(params)]
        return Result()

    def executemany(self, query, rows):
        text = query.as_string()
        table = next(name for name in self.rows if f'"{name}"' in text)
        if table == self.fail_table:
            raise RuntimeError('private driver message containing secret-password')
        self.rows[table].extend(tuple(value.obj if hasattr(value, 'obj') else value for value in row) for row in rows)

    @contextmanager
    def cursor(self):
        yield self


class SourceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for name in ('sessions', 'recordings', 'learning', 'samples'):
            (self.root / name).mkdir()
        self.sid = 'test-ingestion'
        self.meta = json.loads((ROOT / 'contracts/examples/session.json').read_text())
        self.meta.update(session_id=self.sid, player='tester', rounds=[{'round': 1, 'winner': None}, {'round': 2, 'winner': None}])
        self.meta.pop('recording', None)
        self.recording = self.root / 'recordings' / f'{self.sid}.jsonl'
        self.write_meta()
        self.state = json.loads((ROOT / 'contracts/examples/gamestate.json').read_text())
        self.lines = [self.event(1, 4375, 'round_start'), self.frame(1, 4375), self.event(1, 4377, 'hit', actor=1, target=0, damage=5), self.event(1, 4377, 'hit', actor=1, target=0, damage=5), self.frame(1, 4377), self.event(1, 4377, 'round_end'), self.event(2, 0, 'round_start'), self.frame(2, 0), self.frame(2, 2), self.event(2, 2, 'round_end')]
        self.write_records()

    def write_meta(self):
        (self.root / 'sessions' / f'{self.sid}.json').write_text(json.dumps(self.meta))

    def write_records(self):
        self.recording.write_text(''.join(json.dumps(record) + '\n' for record in self.lines))

    def frame(self, round_, frame):
        return {**copy.deepcopy(self.state), 'session_id': self.sid, 'round': round_, 'frame': frame, 'future_field': True}

    def event(self, round_, frame, kind, **fields):
        return {'t': 'event', 'session_id': self.sid, 'round': round_, 'frame': frame, 'kind': kind, **fields}

    def batches(self):
        return prepare(self.meta, self.recording, self.root)

    def test_nonzero_frames_reset_and_same_frame_events(self):
        first, second = self.batches()
        start = first.rows['frames'][0].observed_at
        self.assertAlmostEqual((first.rows['frames'][1].observed_at - start).total_seconds(), 2 / 60, places=5)
        self.assertAlmostEqual((second.rows['frames'][0].observed_at - start).total_seconds(), 3 / 60, places=5)
        hits = [row for row in first.rows['events'] if row.record['kind'] == 'hit']
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0].observed_at, hits[1].observed_at)
        self.assertNotEqual(hits[0].source_line, hits[1].source_line)
        self.assertTrue(first.rows['frames'][0].record['future_field'])

    def test_only_completed_rounds_and_tolerates_partial_tail(self):
        self.lines.pop()
        self.write_records()
        with self.recording.open('a') as stream:
            stream.write('{"t":"event"')
        self.assertEqual([batch.number for batch in self.batches()], [1])

    def test_summary_also_closes_round_without_frame(self):
        self.lines = [self.frame(1, 100)]
        summary = json.loads((ROOT / 'contracts/examples/round_summary.json').read_text())
        summary.update(session_id=self.sid, round=1)
        summary.pop('frame', None)
        self.lines.append(summary)
        self.write_records()
        self.assertEqual(len(self.batches()), 1)
        self.assertEqual(len(self.batches()[0].rows['round_metrics']), 2)

    def test_unknown_records_ignored_and_learning_is_raw(self):
        self.lines.insert(0, {'t': 'future_record', 'round': 99, 'frame': 999999})
        self.write_records()
        learning = {'t': 'learning_round', 'session_id': self.sid, 'round': 1, 'prediction_accuracy': 0.4, 'habits': {}, 'future': True, 'frame': 'unknown-extension'}
        (self.root / 'learning' / f'{self.sid}.jsonl').write_text(json.dumps(learning) + '\n')
        first = self.batches()[0]
        self.assertEqual(first.rows['round_metrics'][0].record, learning)
        self.assertEqual(first.rows['round_metrics'][0].source, 'learning')

    def test_corrected_round_duration_moves_later_round_timestamps(self):
        before = self.batches()
        self.lines[5]['frame'] = 4387
        self.write_records()
        after = self.batches()
        self.assertNotEqual(before[1].fingerprint, after[1].fingerprint)
        self.assertAlmostEqual((after[1].rows['frames'][0].observed_at - before[1].rows['frames'][0].observed_at).total_seconds(), 10 / 60, places=5)

    def test_out_of_range_timestamp_is_an_input_error(self):
        self.lines[1]['frame'] = 10 ** 400
        self.write_records()
        with self.assertRaisesRegex(InputError, 'out-of-range frame timing'):
            self.batches()

    def test_invalid_complete_records_fail_with_file_line(self):
        self.recording.write_text('{"t":"event"}\n')
        with self.assertRaisesRegex(InputError, 'test-ingestion.jsonl:1'):
            self.batches()
        self.recording.write_text('not-json\n')
        with self.assertRaisesRegex(InputError, 'malformed JSON'):
            self.batches()

    def test_session_mismatch_fails(self):
        self.lines[1]['session_id'] = 'another-session'
        self.write_records()
        with self.assertRaisesRegex(InputError, 'session id mismatch'):
            self.batches()

    def test_discovery_canonical_precedence_and_sample_pairing(self):
        sample = self.root / 'samples' / 'arbitrary-name.jsonl'
        sample.write_text(self.recording.read_text())
        sample.with_suffix('.session.json').write_text(json.dumps({**self.meta, 'player': 'sample-player'}))
        found = discover(self.root)
        self.assertEqual(found[self.sid][0]['player'], 'tester')
        self.recording.unlink()
        self.assertEqual(discover(self.root)[self.sid][1], sample)
        (self.root / 'sessions' / f'{self.sid}.json').unlink()
        self.assertEqual(discover(self.root)[self.sid][0]['player'], 'sample-player')

    @unittest.skipUnless(importlib.util.find_spec('psycopg'), 'Install Tiger Data optional dependencies')
    def test_same_input_skip_changed_round_replace_and_late_learning(self):
        conn = FakeConnection()
        db = Database(conn)
        self.assertEqual(import_once(self.root, db), (2, 0, 0))
        original_count = len(conn.rows['events'])
        self.assertEqual(import_once(self.root, db), (0, 2, 0))
        self.assertEqual(len(conn.rows['events']), original_count)
        self.lines[2]['damage'] = 20
        self.write_records()
        self.assertEqual(import_once(self.root, db), (1, 1, 0))
        self.assertEqual(len(conn.rows['events']), original_count)
        learning = {'t': 'learning_round', 'round': 1, 'prediction_accuracy': 0.7, 'habits': {}}
        (self.root / 'learning' / f'{self.sid}.jsonl').write_text(json.dumps(learning) + '\n')
        self.assertEqual(import_once(self.root, db), (1, 1, 0))
        self.assertEqual(len(conn.rows['round_metrics']), 3)

    @unittest.skipUnless(importlib.util.find_spec('psycopg'), 'Install Tiger Data optional dependencies')
    def test_transaction_rollback_preserves_previous_rows_and_checkpoint(self):
        conn = FakeConnection()
        db = Database(conn)
        batch = self.batches()[0]
        db.ingest(batch)
        previous = copy.deepcopy((conn.sessions, conn.checkpoints, conn.rows))
        conn.fail_table = 'events'
        with self.assertRaises(DatabaseError) as error:
            db.ingest(replace(batch, fingerprint='changed'))
        self.assertNotIn('secret-password', str(error.exception))
        self.assertEqual((conn.sessions, conn.checkpoints, conn.rows), previous)
        self.assertEqual(conn.rollbacks, 1)
        conn.fail_table = None
        self.assertTrue(db.ingest(replace(batch, fingerprint='changed')))

    @unittest.skipUnless(importlib.util.find_spec('psycopg'), 'Install Tiger Data optional dependencies')
    def test_invalid_session_does_not_hide_good_session_count(self):
        self.lines[1]['players'] = []
        self.write_records()
        with self.assertLogs('analytics.tigerdata', level='WARNING'):
            self.assertEqual(import_once(self.root, Database(FakeConnection())), (0, 0, 1))


class CommandTest(unittest.TestCase):
    def test_url_required_and_never_printed(self):
        with patch.dict(os.environ, {}, clear=True), self.assertLogs('analytics.tigerdata', level='ERROR') as logs:
            self.assertEqual(main(['backfill']), 2)
        self.assertIn('DATABASE_URL', '\n'.join(logs.output))

    def test_unexpected_driver_failure_is_sanitized(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'secret-url'}), patch('analytics.tigerdata.__main__.connection', side_effect=RuntimeError('secret-url')), self.assertLogs('analytics.tigerdata', level='WARNING') as logs:
            self.assertEqual(main(['backfill']), 1)
        self.assertNotIn('secret-url', '\n'.join(logs.output))

    def test_database_outage_watch_retries(self):
        class StopWatch(Exception):
            pass

        with patch.dict(os.environ, {'DATABASE_URL': 'secret-url'}), patch('analytics.tigerdata.__main__.connection', side_effect=DatabaseError('Database connection failed')) as connect, patch('analytics.tigerdata.__main__.time.sleep', side_effect=[None, StopWatch]), self.assertLogs('analytics.tigerdata', level='WARNING') as logs:
            with self.assertRaises(StopWatch):
                main(['watch'])
        self.assertEqual(connect.call_count, 2)
        self.assertNotIn('secret-url', '\n'.join(logs.output))


if __name__ == '__main__':
    unittest.main()
