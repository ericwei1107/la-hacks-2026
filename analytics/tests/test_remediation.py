import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

os.environ['SENTRY_DSN'] = ''

from fastapi.testclient import TestClient
from analytics.main import create_app, VERSION
from analytics.repository import ROOT, DataError, FileRepository, read_lines
from analytics.stats import compute
from analytics.tigerdata.source import prepare
from analytics.tigerdata.trends import signature, snapshot
from analytics.tigerdata.repository import TigerRepository
from analytics.tigerdata.database import Database, DatabaseError, connection
from analytics.tigerdata.__main__ import import_once


class RemediationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for folder in ('sessions', 'recordings', 'learning', 'eval'):
            (self.root / folder).mkdir()
        self.sid = 'audit-session'
        self.meta = json.loads((ROOT / 'contracts/examples/session.json').read_text())
        self.meta.update(session_id=self.sid, player='audit', rounds=[])
        self.meta.pop('recording', None)
        self.meta_path = self.root / 'sessions' / f'{self.sid}.json'
        self.meta_path.write_text(json.dumps(self.meta))
        self.path = self.root / 'recordings' / f'{self.sid}.jsonl'
        self.path.write_text('')
        self.repo = FileRepository(self.root)
        with patch.dict(os.environ, {'DATABASE_URL': ''}):
            self.client = TestClient(create_app(self.root), raise_server_exceptions=False)

    def event(self, frame, kind, **fields):
        return {'t': 'event', 'session_id': self.sid, 'round': 1, 'frame': frame, 'kind': kind, **fields}

    def state(self, frame=0):
        state = json.loads((ROOT / 'contracts/examples/gamestate.json').read_text())
        state.update(session_id=self.sid, round=1, frame=frame)
        state['derived']['situation'] = 'defense'
        return state

    def write(self, records):
        self.path.write_text(''.join(json.dumps(record) + '\n' for record in records))

    def test_hand_calculated_file_and_database_situations_and_winners(self):
        summary = json.loads((ROOT / 'contracts/examples/round_summary.json').read_text())
        summary.update(session_id=self.sid, round=1, winner=0)
        self.write([self.state(), self.event(1, 'hit', actor=1, target=0, damage=10), summary])
        totals = self.repo.stats(self.sid)['totals']
        values = self.repo.trends('audit', self.meta['human_character'])['series'][0]['values']
        self.assertEqual(totals['damage_taken_by_situation'], {'defense': 10})
        self.assertEqual(totals['rounds_won'], 1)
        self.assertEqual(values['damage_taken_by_situation:defense'], 10)
        self.assertNotIn('damage_taken_by_situation:neutral', values)
        self.assertEqual(values['rounds_won'], 1)
        self.assertEqual(values[f"win_rate:difficulty:{self.meta['difficulty']}"], 1)
        batches = prepare(self.meta, self.path, self.root)
        calculated = next(row.record for row in batches[0].rows['round_metrics'] if row.source == 'calculated')
        self.assertEqual(calculated['damage_taken_by_situation'], {'defense': 10})
        self.assertEqual(calculated['rounds_won'], 1)
        derived = snapshot(self.root, self.meta, self.path, batches)
        self.assertIn(('damage_taken_by_situation:defense', 10), [(row[3], row[4]) for row in derived.rows])

    def test_punishes_are_one_to_one_for_both_slots_and_rounds(self):
        for human in (0, 1):
            bot = 1 - human
            records = [self.event(10, 'block', actor=bot, target=human, frame_advantage=-12), self.event(15, 'block', actor=bot, target=human, frame_advantage=-12), self.event(20, 'hit', actor=human, target=bot)]
            records.append({**self.event(0, 'hit', actor=human, target=bot), 'round': 2})
            totals = compute(self.sid, {'human_slot': human, 'rounds': []}, records)['totals']
            self.assertEqual(totals['punish_rate'], 0.5)

    def test_last_non_null_winner_preserves_metadata_and_source_order(self):
        records = [self.event(1, 'round_end', detail={'winner': 1}), {'t': 'round_summary', 'round': 1, 'winner': 0}, self.event(2, 'round_end', detail={'winner': None})]
        self.assertEqual(compute(self.sid, self.meta, records)['totals']['rounds_won'], 1)

    def test_malformed_known_records_and_unknown_types_do_not_crash_stats(self):
        self.write([self.event(1, 'hit', actor=1, target=0, damage=10), self.event(2, 'hit', actor=1, target=0, damage='bad'), {'t': 'future', 'round': 99}, {**self.event(3, 'hit', actor=1, target=0, damage=30), 'session_id': 'wrong'}])
        response = self.client.get(f'/stats/{self.sid}')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['totals']['damage_taken_by_situation'], {'neutral': 10})
        self.assertEqual([r['round'] for r in body['rounds']], [1])
        self.assertEqual(body['skipped_lines'], 2)
        self.assertEqual(self.client.get('/trends/audit/' + self.meta['human_character']).status_code, 503)

    def test_larger_replacement_and_same_inode_correction_refresh_stats(self):
        old = self.event(1, 'hit', actor=1, target=0, damage=10)
        self.write([old])
        self.assertEqual(self.repo.stats(self.sid)['totals']['damage_taken_by_situation'], {'neutral': 10})
        replacement = self.path.with_suffix('.tmp')
        replacement.write_text(json.dumps({**old, 'damage': 100, 'future': 'larger'}) + '\n')
        os.replace(replacement, self.path)
        self.assertEqual(self.repo.stats(self.sid)['totals']['damage_taken_by_situation'], {'neutral': 100})
        self.write([{**old, 'damage': 120, 'future': 'even larger correction'}])
        self.assertEqual(self.repo.stats(self.sid)['totals']['damage_taken_by_situation'], {'neutral': 120})

    def test_partial_literals_are_pending_but_complete_malformed_lines_fail(self):
        for suffix in ('tru', 'fals', 'nul', '1e+', '1.', '"abc', '"\\u12'):
            partial = '{"t":"learning_round","future":' + suffix
            self.assertEqual(read_lines(partial, 'tail'), [])
            with self.assertRaises(DataError):
                read_lines(partial + '\n', 'tail')
        with self.assertRaises(DataError):
            read_lines('{"t":broken}', 'tail')

    def test_invalid_metadata_is_isolated_and_imports_count_it(self):
        self.write([self.state(), self.event(1, 'round_end', detail={'winner': 0})])
        (self.root / 'sessions/broken.json').write_text('{broken')
        self.assertEqual(self.client.get(f'/stats/{self.sid}').status_code, 200)
        self.assertEqual(self.client.get(f'/learning/{self.sid}').status_code, 200)
        self.assertEqual(self.client.get('/stats/broken').status_code, 503)
        self.assertEqual(len(self.repo.trends('audit', self.meta['human_character'])['series']), 1)
        from test_tigerdata import FakeConnection
        self.assertEqual(import_once(self.root, Database(FakeConnection())), (1, 0, 1))

    def test_calculation_version_invalidates_rounds_and_aggregate_signatures(self):
        self.write([self.state(), self.event(1, 'round_end')])
        before_round = prepare(self.meta, self.path, self.root)[0].fingerprint
        before_trend = signature(self.repo, self.meta, self.path)
        with patch('analytics.stats.CALCULATION_VERSION', 999):
            self.assertNotEqual(prepare(self.meta, self.path, self.root)[0].fingerprint, before_round)
            self.assertNotEqual(signature(self.repo, self.meta, self.path), before_trend)

    def test_slow_database_does_not_hold_file_lock_or_queue_other_trends(self):
        self.write([self.state()])
        repo = TigerRepository(self.root, 'private-url')
        entered, release = threading.Event(), threading.Event()
        def unavailable(*args, **kwargs):
            self.assertTrue(kwargs['api'])
            entered.set()
            release.wait(5)
            raise DatabaseError('unavailable')
        with patch('analytics.tigerdata.repository.connection', side_effect=unavailable), ThreadPoolExecutor(4) as pool:
            pending = pool.submit(repo.trends, 'audit', self.meta['human_character'])
            try:
                self.assertTrue(entered.wait(2))
                self.assertIsNotNone(pool.submit(repo.stats, self.sid).result(timeout=1))
                self.assertIsNotNone(pool.submit(repo.learning, self.sid).result(timeout=1))
                self.assertEqual(len(pool.submit(repo.trends, 'audit', self.meta['human_character']).result(timeout=1)['series']), 1)
            finally:
                release.set()
            self.assertEqual(len(pending.result(timeout=2)['series']), 1)

    def test_api_connections_use_short_limits_and_importers_keep_long_limits(self):
        with patch('psycopg.connect') as connect:
            connection('private-url', api=True)
            self.assertEqual(connect.call_args.kwargs['connect_timeout'], 2)
            self.assertIn('statement_timeout=2000', connect.call_args.kwargs['options'])
            connection('private-url')
            self.assertEqual(connect.call_args.kwargs['connect_timeout'], 5)
            self.assertIn('statement_timeout=15000', connect.call_args.kwargs['options'])

    def test_health_version_is_git_sha_even_with_release_override(self):
        self.assertEqual(self.client.get('/health').json()['version'], VERSION)
        self.assertNotIn('kumite-analytics@', VERSION)


if __name__ == '__main__':
    unittest.main()
