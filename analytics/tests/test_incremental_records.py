import json
import os
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['SENTRY_DSN'] = ''

from fastapi.testclient import TestClient
from analytics.main import create_app
from analytics.metrics import trend_values
from analytics.repository import ROOT, DataError, FileRepository, decode
from analytics.stats import compute, rate


class IncrementalRecordsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('sessions', 'recordings', 'learning'):
            (self.root / name).mkdir()
        self.sid = 'incremental-session'
        self.meta = json.loads((ROOT / 'contracts/examples/session.json').read_text())
        self.meta.update(session_id=self.sid, player='alice', started_at='2026-10-17T13:00:00Z', difficulty=3, rounds=[{'round': 1, 'winner': 1}])
        self.meta.pop('recording', None)
        (self.root / 'sessions' / f'{self.sid}.json').write_text(json.dumps(self.meta))
        self.path = self.root / 'recordings' / f'{self.sid}.jsonl'
        self.path.write_text(self.lines([self.event(1, 'hit', actor=1, target=0, damage=10)]))
        patcher = patch.dict(os.environ, {'DATABASE_URL': ''})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.repository = FileRepository(self.root)

    def event(self, frame, kind, **fields):
        return {'t': 'event', 'session_id': self.sid, 'round': 1, 'frame': frame, 'kind': kind, **fields}

    def lines(self, records):
        return ''.join(json.dumps(record) + '\n' for record in records)

    def append(self, text):
        with self.path.open('a') as stream:
            stream.write(text)

    def test_appended_lines_extend_the_same_tail_without_a_full_reparse(self):
        stamp, records = self.repository._records(self.path, self.sid)
        tail = self.repository.tails[self.path]
        generation, offset = tail.generation, tail.offset
        self.assertEqual(len(records), 1)
        self.append(self.lines([self.event(2, 'hit', actor=1, target=0, damage=5)]))
        with patch('analytics.repository.decode', wraps=decode) as spy:
            stamp2, records2 = self.repository._records(self.path, self.sid)
        self.assertIs(self.repository.tails[self.path], tail)
        self.assertEqual(tail.generation, generation)
        self.assertGreater(tail.offset, offset)
        self.assertNotEqual(stamp, stamp2)
        self.assertEqual([r['frame'] for r in records2], [1, 2])
        self.assertEqual(spy.call_count, 1)

    def test_unchanged_file_returns_the_cached_list(self):
        first = self.repository._records(self.path, self.sid)
        second = self.repository._records(self.path, self.sid)
        self.assertIs(first[1], second[1])

    def test_partial_last_line_is_pending_until_completed(self):
        self.append('{"t":"event","session_id":"' + self.sid + '","round":1,"frame":2,')
        self.assertEqual(len(self.repository._records(self.path, self.sid)[1]), 1)
        self.append('"kind":"hit","actor":1,"target":0,"damage":4}\n')
        self.assertEqual([r['frame'] for r in self.repository._records(self.path, self.sid)[1]], [1, 2])

    def test_trends_stay_strict_and_name_the_line(self):
        self.append('{"t":"event","oops\n')
        with self.assertRaisesRegex(DataError, r'incremental-session\.jsonl:2: invalid JSON'):
            self.repository._records(self.path, self.sid)
        self.path.write_text(self.lines([self.event(1, 'hit', actor=1, target=0, damage=10), self.event(2, 'not-a-kind')]))
        with self.assertRaisesRegex(DataError, r'incremental-session\.jsonl:2: invalid data at kind'):
            self.repository._records(self.path, self.sid)
        client = TestClient(create_app(self.root))
        self.assertEqual(client.get('/trends/alice/' + self.meta['human_character']).status_code, 503)
        self.assertEqual(client.get(f'/stats/{self.sid}').status_code, 200)

    def test_rewritten_file_resets_the_tail(self):
        self.repository._records(self.path, self.sid)
        generation = self.repository.tails[self.path].generation
        self.path.write_text(self.lines([self.event(7, 'hit', actor=1, target=0, damage=3)]))
        _, records = self.repository._records(self.path, self.sid)
        self.assertEqual([r['frame'] for r in records], [7])
        self.assertEqual(self.repository.tails[self.path].generation, generation + 1)

    def test_stats_and_trends_share_one_tail(self):
        self.repository.stats(self.sid)
        recording = self.repository._sessions()[self.sid][3]
        self.repository._records(recording, self.sid)
        self.assertEqual(list(self.repository.tails), [recording])

    def test_tail_is_not_shared_across_session_ids(self):
        self.repository._records(self.path, self.sid)
        other = self.event(1, 'hit', actor=1, target=0, damage=10)
        other['session_id'] = 'someone-else'
        self.path.write_text(self.lines([other]))
        with self.assertRaises(DataError):
            self.repository._records(self.path, self.sid)

    def test_missing_recording_is_a_data_error(self):
        self.path.unlink()
        with self.assertRaisesRegex(DataError, 'required file is missing'):
            self.repository._records(self.path, self.sid)

    def test_trend_values_match_a_cold_read_after_incremental_appends(self):
        self.repository._records(self.path, self.sid)
        for frame in range(2, 12):
            self.append(self.lines([self.event(frame, 'hit', actor=1, target=0, damage=frame)]))
            self.repository._records(self.path, self.sid)
        grown = self.repository.trends('alice', self.meta['human_character'])
        cold = FileRepository(self.root).trends('alice', self.meta['human_character'])
        self.assertEqual(grown, cold)

    def test_append_between_the_two_stat_calls_is_retried_not_an_error(self):
        real = os.fstat
        calls = []

        def racing(descriptor):
            actual = real(descriptor)
            calls.append(actual)
            if len(calls) == 2:
                return SimpleNamespace(st_dev=actual.st_dev, st_ino=actual.st_ino, st_size=actual.st_size + 17, st_mtime_ns=actual.st_mtime_ns + 1)
            return actual

        with patch('analytics.repository.os.fstat', side_effect=racing):
            stamp, records = self.repository._records(self.path, self.sid)
        self.assertEqual(len(records), 1)
        self.assertGreater(len(calls), 2)

    def test_a_file_that_never_settles_still_reports_a_retryable_error(self):
        real = os.fstat
        count = []

        def unstable(descriptor):
            actual = real(descriptor)
            count.append(1)
            bump = len(count) % 2 == 0
            return SimpleNamespace(st_dev=actual.st_dev, st_ino=actual.st_ino, st_size=actual.st_size + bump, st_mtime_ns=actual.st_mtime_ns + bump)

        with patch('analytics.repository.os.fstat', side_effect=unstable):
            with self.assertRaisesRegex(DataError, 'changed while being read'):
                self.repository._records(self.path, self.sid)


class ImpossibleRateTest(unittest.TestCase):
    def test_rate_is_null_when_successes_exceed_opportunities(self):
        self.assertIsNone(rate(3, 1))
        self.assertIsNone(rate(1, 0))
        self.assertEqual(rate(2, 3), 0.667)
        self.assertEqual(rate(0, 4), 0.0)
        self.assertEqual(rate(4, 4), 1.0)

    def test_more_breaks_than_throws_is_not_reported_as_a_perfect_rate(self):
        meta = {'session_id': 's', 'human_slot': 0, 'rounds': []}
        throw = {'t': 'event', 'session_id': 's', 'round': 1, 'frame': 10, 'kind': 'throw', 'actor': 1, 'target': 0}
        breaks = [{'t': 'event', 'session_id': 's', 'round': 1, 'frame': 12 + i, 'kind': 'throw_break', 'actor': 0, 'target': 1} for i in range(3)]
        totals = compute('s', meta, [throw] + breaks)['totals']
        self.assertIsNone(totals['throw_break_rate'])
        self.assertEqual(sum(totals['throw_breaks_by_type'].values()), 3)
        self.assertEqual(compute('s', meta, [throw, breaks[0]])['totals']['throw_break_rate'], 1.0)

    def test_win_rate_uses_the_shared_rate(self):
        meta = {'session_id': 's', 'human_slot': 0, 'difficulty': 3, 'rounds': [{'round': 1, 'winner': 0}, {'round': 2, 'winner': 1}, {'round': 3, 'winner': 1}]}
        values = trend_values(meta, [], {'rounds': [], 'time_to_mastery': {}})
        self.assertEqual(values['win_rate:difficulty:3'], 0.333)


if __name__ == '__main__':
    unittest.main()
