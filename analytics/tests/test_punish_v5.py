import copy
import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from analytics.evidence import analyze
from analytics.stats import CALCULATION_VERSION, compute, opportunities
from analytics.repository import FileRepository, ROOT
from analytics.tigerdata.source import discover, prepare
from analytics.tigerdata.trends import signature, snapshot
from analytics.tigerdata.database import Database
from analytics.tigerdata.__main__ import import_once, main, plan
from analytics.repository import DataError
from analytics.tigerdata.source import InputError
from test_tigerdata import FakeConnection
from punish_fixtures import timed

SID = '2026-10-18T05-14-03_sahil_djin_vs_kaz'
REAL = ROOT / 'data/samples/live_learning'


def event(frame, kind='hit', human=0, round_=1, **fields):
    return {'t': 'event', 'session_id': 's', 'frame': frame, 'round': round_, 'kind': kind,
            'actor': human, 'target': 1-human, **fields}


class PunishV5Test(unittest.TestCase):
    def records(self, human=0):
        return timed(event(10, 'block', human=1-human, frame_advantage=-12), human, human_free=29)

    def rate(self, records, human=0):
        return compute('s', {'human_slot': human}, records)['totals']['punish_rate']

    def test_exact_recovery_boundary_without_tolerance_for_both_slots(self):
        for human in (0, 1):
            for kind in ('hit', 'counter_hit'):
                for frame, expected in ((29, 0.), (40, 1.), (41, 1.), (42, 0.)):
                    with self.subTest(human=human, kind=kind, frame=frame):
                        self.assertEqual(self.rate(self.records(human) + [event(frame, kind, human)], human), expected)

    def test_late_string_continuation_despite_false_producer_flag(self):
        records = self.records()
        for state in records[1:]:
            if state['frame'] >= 20:
                state['players'][1]['move_id'] = 43
        self.assertIsNone(self.rate(records + [event(40)]))
        found = opportunities([r for r in records if r['t'] == 'event'], 0, records)
        self.assertEqual(found['punish_excluded'][0][1], 'continuation')

    def test_same_move_restart_is_a_continuation(self):
        records = self.records()
        records[12]['players'][1]['frame_in_move'] = 1
        self.assertIsNone(self.rate(records))

    def test_continuation_at_response_frame_before_recovery_is_not_a_punish(self):
        records = self.records()
        records[-2]['players'][1]['move_id'] = 43
        self.assertIsNone(self.rate(records + [event(40)]))

    def test_conflicting_state_and_recovery_counters_remain_uncertain(self):
        records = self.records()
        duplicate = copy.deepcopy(records[1])
        duplicate['players'][1]['frame_in_move'] += 1
        self.assertIsNone(self.rate(records + [duplicate, event(40)]))
        records = self.records()
        records[1]['players'][0]['frames_until_actionable'] += 1
        self.assertIsNone(self.rate(records + [event(40)]))

    def test_missing_inconsistent_or_gapped_evidence_is_uncertain(self):
        variants = []
        records = self.records()
        variants.append(records[:1])
        variants.append(records[:5] + records[6:])
        for key, value in (('read_frame', True), ('attacker_total', 100), ('defender_frame', -1)):
            changed = copy.deepcopy(records)
            changed[0]['detail'][key] = value
            variants.append(changed)
        variants.append([event(10, 'block', human=1, frame_advantage=-12)])
        for records in variants:
            self.assertIsNone(self.rate(records + [event(40)]))
            result = analyze(list(enumerate(records + [event(40)], 1)), 0, 's', 'hash')['punish_conversion']
            self.assertEqual(result['state'], 'invalid')
            self.assertIsNone(result['value'])
            self.assertEqual(result['anomalies'][0]['kind'], 'uncertain_punish_timing')

    def test_round_and_target_isolation(self):
        for hit in (event(40, round_=2), event(40, target=0)):
            self.assertEqual(self.rate(self.records() + [hit]), 0.)

    def test_one_hit_only_converts_one_opportunity(self):
        records = self.records()
        records.insert(1, copy.deepcopy(records[0]))
        self.assertEqual(self.rate(records + [event(40)]), .5)
        self.assertEqual(self.rate(records + [event(40), event(41)]), 1.)

    def test_real_audit_shared_stats_evidence_round_and_trend_parity(self):
        repository = FileRepository(REAL)
        meta, recording = discover(REAL)[SID]
        records = [json.loads(line) for line in recording.read_text().splitlines() if line.strip()]
        result = analyze(list(enumerate(records, 1)), 0, SID, 'hash')['punish_conversion']
        self.assertEqual((result['successes'], result['opportunities'], result['value']), (1, 5, .2))
        self.assertEqual(next(row for row in result['evidence'] if row['outcome'] == 'success')['response']['frame'], 1522)
        self.assertEqual(repository.stats(SID)['totals']['punish_rate'], .2)
        batches = prepare(meta, recording, REAL)
        calculated = [row.record['punish_rate'] for batch in batches for row in batch.rows['round_metrics'] if row.source == 'calculated']
        self.assertEqual(calculated, [.5, 0., None, None])
        derived = snapshot(REAL, meta, recording, batches)
        final = {row[3]: row[4] for row in derived.rows if row[2] == 4}
        self.assertEqual(final['punish_rate'], .2)
        self.assertEqual(final, repository.trends(meta['player'], meta['human_character'])['series'][0]['values'])

    def test_version_change_reimports_once_and_republishes_locally(self):
        self.assertEqual(CALCULATION_VERSION, 6)
        conn = FakeConnection()
        database = Database(conn)
        meta, recording = discover(REAL)[SID]
        with patch('analytics.stats.CALCULATION_VERSION', 4):
            old = prepare(meta, recording, REAL)
            old_signature = signature(FileRepository(REAL), meta, recording)
            self.assertEqual(import_once(REAL, database), (4, 0, 0))
        new = prepare(meta, recording, REAL)
        self.assertTrue(all(a.fingerprint != b.fingerprint for a, b in zip(old, new)))
        self.assertNotEqual(old_signature, signature(FileRepository(REAL), meta, recording))
        self.assertEqual(import_once(REAL, database), (4, 0, 0))
        self.assertEqual(import_once(REAL, database), (0, 4, 0))
        self.assertEqual(conn.refreshes, 2)
        self.assertTrue(conn.trend_imports[SID][1])

    def test_local_plan_never_connects_even_with_database_url(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'must-not-connect'}), patch(
                'analytics.tigerdata.__main__.connection', side_effect=AssertionError('cloud connection')):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(['plan', '--data-dir', str(REAL), '--session-id', SID]), 0)
            result = json.loads(output.getvalue())
        self.assertFalse(result['cloud_checked'])
        self.assertFalse(result['cloud_writes'])
        self.assertEqual([row['round'] for row in result['sessions'][0]['rounds']], [1, 2, 3, 4])

    def test_unknown_scope_fails_before_any_database_mutation(self):
        from unittest.mock import Mock
        database = Mock()
        with self.assertRaises(InputError):
            import_once(REAL, database, [SID, 'not-present'])
        database.ingest.assert_not_called()
        database.publish.assert_not_called()

    def test_plan_rejects_source_change_during_preparation(self):
        from unittest.mock import Mock
        with patch('analytics.tigerdata.__main__.prepare', return_value=[]), patch(
                'analytics.tigerdata.__main__.snapshot', return_value=Mock(signature='changed')):
            with self.assertRaises(DataError):
                plan(REAL, [SID])

    def test_scope_excludes_other_discovered_sessions(self):
        sessions = discover(REAL)
        sessions['unapproved'] = ({'session_id': 'unapproved'}, ROOT / 'not-a-recording')
        conn = FakeConnection()
        with patch('analytics.tigerdata.__main__.discover', return_value=sessions):
            self.assertEqual(import_once(REAL, Database(conn), [SID]), (4, 0, 0))
        self.assertEqual(set(conn.sessions), {SID})

    def test_v4_and_v5_cloud_signatures_fall_back_to_corrected_files(self):
        from analytics.tigerdata.repository import TigerRepository

        meta, recording = discover(REAL)[SID]
        for previous_version in (4, 5):
            with self.subTest(previous_version=previous_version):
                with patch('analytics.stats.CALCULATION_VERSION', previous_version):
                    stale = signature(FileRepository(REAL), meta, recording)
                repository = TigerRepository(REAL, 'must-not-connect')
                with patch('analytics.tigerdata.repository.connection'), patch.object(Database, 'trends',
                        return_value={SID: (stale, {'punish_rate': 0.})}):
                    values = repository.trends(meta['player'], meta['human_character'])['series'][0]['values']
                self.assertEqual(values['punish_rate'], .2)


if __name__ == '__main__':
    unittest.main()
