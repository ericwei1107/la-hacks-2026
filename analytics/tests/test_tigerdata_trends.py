import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from analytics.metrics import trend_values
from analytics.repository import FileRepository
from analytics.tigerdata.database import Database, DatabaseError
from analytics.tigerdata.repository import TigerRepository
from analytics.tigerdata.source import ROOT, discover, prepare
from analytics.tigerdata.trends import snapshot
from test_tigerdata import FakeConnection


class TigerTrendsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        samples = self.root / 'samples'
        samples.mkdir()
        for path in (ROOT / 'tools/mock/tests/fixtures').glob('two-rounds*'):
            (samples / path.name).write_bytes(path.read_bytes())
        self.sid, (self.meta, self.recording) = next(iter(discover(self.root).items()))
        self.files = FileRepository(self.root)
        self.repository = TigerRepository(self.root, 'secret-url')

    def derived(self):
        return snapshot(self.root, self.meta, self.recording, prepare(self.meta, self.recording, self.root))

    def stored(self):
        derived = self.derived()
        number = max(row[2] for row in derived.rows)
        return {self.sid: (derived.signature, {row[3]: row[4] for row in derived.rows if row[2] == number})}

    def expected(self, stat=None):
        return self.files.trends(self.meta['player'], self.meta['human_character'], stat)

    def fetch(self, stat=None):
        return self.repository.trends(self.meta['player'], self.meta['human_character'], stat)

    def test_database_read_rejects_incomplete_and_nonfinite_aggregates(self):
        conn = MagicMock()
        database = Database(conn)
        conn.execute.return_value.fetchall.return_value = [(self.sid, 'version', 2, 'punish_rate', None)]
        self.assertEqual(database.trends([self.sid]), {})
        conn.execute.return_value.fetchall.return_value = [(self.sid, 'version', 1, 'punish_rate', None)]
        self.assertEqual(database.trends([self.sid]), {self.sid: ('version', {'punish_rate': None})})
        conn.execute.return_value.fetchall.return_value = [(self.sid, 'version', 1, 'punish_rate', float('nan'))]
        with self.assertRaises(DatabaseError):
            database.trends([self.sid])

    def test_database_catalogue_keeps_order_and_exact_isolation(self):
        stored = self.stored()
        samples = self.root / 'samples'
        for sid, player, character, started in [('earlier', self.meta['player'], self.meta['human_character'], '2020-01-01T00:00:00Z'), ('other-player', 'someone-else', self.meta['human_character'], self.meta['started_at']), ('other-character', self.meta['player'], 'king', self.meta['started_at'])]:
            meta = {**self.meta, 'session_id': sid, 'player': player, 'human_character': character, 'started_at': started}
            (samples / f'{sid}.session.json').write_text(json.dumps(meta))
            records = [json.loads(line) for line in self.recording.read_text().splitlines()]
            (samples / f'{sid}.jsonl').write_text(''.join(json.dumps({**record, 'session_id': sid}) + '\n' for record in records))
        with patch('analytics.tigerdata.repository.connection'), patch.object(Database, 'trends', return_value=stored) as query:
            result = self.fetch()
            self.assertEqual(result, self.expected())
            self.assertEqual([point['session_id'] for point in result['series']], ['earlier', self.sid])
            self.assertEqual(set(query.call_args.args[0]), {'earlier', self.sid})

    def test_metadata_recording_and_evaluation_updates_invalidate_snapshot(self):
        stored = self.stored()
        records = [json.loads(line) for line in self.recording.read_text().splitlines()]
        event = next(record for record in records if record['t'] == 'event')
        event.update(kind='counter_hit', actor=self.meta['human_slot'], target=1-self.meta['human_slot'], damage=17)
        self.recording.write_text(''.join(json.dumps(record) + '\n' for record in records))
        with patch('analytics.tigerdata.repository.connection'), patch.object(Database, 'trends', return_value=stored):
            self.assertEqual(self.fetch(), self.expected())
        stored = self.stored()
        (self.root / 'eval').mkdir()
        (self.root / 'eval' / f'{self.sid}.json').write_text('{"before":0.41,"after":0.71}')
        with patch('analytics.tigerdata.repository.connection'), patch.object(Database, 'trends', return_value=stored), patch('analytics.tigerdata.repository.trend_values', wraps=trend_values) as reducer:
            self.assertEqual(self.fetch(), self.expected())
            self.assertEqual(reducer.call_count, 1)
        (self.root / 'samples' / 'two-rounds.session.json').write_text(json.dumps({**self.meta, 'difficulty': 5}))
        with patch('analytics.tigerdata.repository.connection'), patch.object(Database, 'trends', return_value=stored):
            self.assertEqual(self.fetch(), self.expected())
            self.assertIn('win_rate:difficulty:5', self.fetch()['series'][0]['values'])

    def test_snapshots_match_file_values_and_calculated_rounds(self):
        batches = prepare(self.meta, self.recording, self.root)
        calculated = [row.record for batch in batches for row in batch.rows['round_metrics'] if row.source == 'calculated']
        self.assertEqual(len(calculated), 2)
        self.assertTrue(all('punish_rate' in row for row in calculated))
        self.assertTrue(self.derived().eligible)
        self.assertEqual(self.stored()[self.sid][1], self.expected()['series'][0]['values'])

    def test_database_path_preserves_filter_nulls_and_avoids_reducer(self):
        stored = self.stored()
        with patch('analytics.tigerdata.repository.connection'), patch.object(Database, 'trends', return_value=stored), patch('analytics.tigerdata.repository.trend_values', side_effect=AssertionError('File reducer called')):
            self.assertEqual(self.fetch(), self.expected())
            self.assertEqual(self.fetch('missing'), self.expected('missing'))
            self.assertEqual(self.fetch('punish_rate'), self.expected('punish_rate'))

    def test_lagging_missing_and_changed_files_fall_back(self):
        stored = self.stored()
        with patch('analytics.tigerdata.repository.connection'), patch.object(Database, 'trends', return_value={}):
            self.assertEqual(self.fetch(), self.expected())
        (self.root / 'learning').mkdir()
        path = self.root / 'learning' / f'{self.sid}.jsonl'
        path.write_text(json.dumps({'t': 'learning_round', 'round': 1, 'prediction_accuracy': 0.7, 'habits': {'low_defense': {'n': 4, 'p': 0.8, 'mastery': 0.9, 'fixed': True}}}) + '\n')
        with patch('analytics.tigerdata.repository.connection'), patch.object(Database, 'trends', return_value=stored):
            response = self.fetch()
            self.assertEqual(response, self.expected())
            self.assertEqual(response['series'][0]['values']['habit_probability:low_defense'], 0.8)
        self.assertNotEqual(self.derived().signature, stored[self.sid][0])

    def test_outage_retry_and_recovery_does_not_expose_credentials(self):
        with patch('analytics.tigerdata.repository.connection', side_effect=RuntimeError('secret-url')) as connect, self.assertLogs('analytics.tigerdata', level='WARNING') as logs:
            self.assertEqual(self.fetch(), self.expected())
            self.assertEqual(self.fetch(), self.expected())
            self.assertEqual(connect.call_count, 1)
        self.assertNotIn('secret-url', '\n'.join(logs.output))
        with patch('analytics.tigerdata.repository.time.monotonic', return_value=self.repository.retry_at + 1), patch('analytics.tigerdata.repository.connection'), patch.object(Database, 'trends', return_value=self.stored()), patch('analytics.tigerdata.repository.trend_values', side_effect=AssertionError):
            self.assertEqual(self.fetch(), self.expected())

    def test_active_round_blocks_database_publication(self):
        with self.recording.open('a') as stream:
            stream.write(json.dumps({'t': 'event', 'round': 3, 'frame': 0, 'session_id': self.sid, 'kind': 'round_start'}) + '\n')
        derived = self.derived()
        self.assertFalse(derived.eligible)
        self.assertEqual({row[2] for row in derived.rows}, {1, 2})

    def test_failed_refresh_is_unavailable_and_retried(self):
        conn = FakeConnection()
        database = Database(conn)
        derived = self.derived()
        conn.fail_refresh = True
        with self.assertRaises(DatabaseError):
            database.publish(derived)
        self.assertFalse(conn.trend_imports[self.sid][1])
        conn.fail_refresh = False
        database.publish(derived)
        self.assertTrue(conn.trend_imports[self.sid][1])
        count = len(conn.rows['trend_snapshots'])
        database.publish(derived)
        self.assertEqual(len(conn.rows['trend_snapshots']), count)
        self.assertEqual(conn.refreshes, 1)

    def test_snapshot_transaction_rolls_back_and_corrections_replace(self):
        conn = FakeConnection()
        database = Database(conn)
        derived = self.derived()
        database.publish(derived)
        original = list(conn.rows['trend_snapshots'])
        conn.fail_table = 'trend_snapshots'
        with self.assertRaises(DatabaseError):
            database.publish(replace(derived, signature='new'))
        self.assertEqual(conn.rows['trend_snapshots'], original)
        self.assertEqual(conn.trend_imports[self.sid][0], derived.signature)
        conn.fail_table = None
        database.publish(replace(derived, signature='new', rows=[(*row[:4], 0.5) for row in derived.rows]))
        self.assertEqual(len(conn.rows['trend_snapshots']), len(original))
        self.assertTrue(all(row[4] == 0.5 for row in conn.rows['trend_snapshots']))

    def test_invalid_local_file_returns_503_even_with_database_available(self):
        from analytics.main import create_app

        with patch.dict(os.environ, {'DATABASE_URL': 'secret-url'}):
            app = create_app(self.root)
        stored = self.stored()
        self.recording.write_text('{"t":"event"}\n')
        with patch('analytics.tigerdata.repository.connection'), patch.object(Database, 'trends', return_value=stored), TestClient(app) as client:
            self.assertEqual(client.get(f"/trends/{self.meta['player']}/{self.meta['human_character']}").status_code, 503)
            self.assertEqual(client.get('/health').status_code, 200)


if __name__ == '__main__':
    unittest.main()
