import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['SENTRY_DSN'] = ''

from analytics.evidence import analyze
from analytics.focus import select
from analytics.insights import InsightRepository, check_id, encoded, prefix, write_export
from analytics.repository import DataError, ROOT
from analytics.stats import CALCULATION_VERSION, Situations, block


def event(frame, kind='hit', round_=1, **fields):
    return {'t': 'event', 'session_id': 's', 'round': round_, 'frame': frame, 'kind': kind, **fields}


def summary(round_=1):
    value = json.loads((ROOT / 'contracts/examples/round_summary.json').read_text())
    value.update(session_id='s', round=round_)
    return value


class MetricEvidenceTest(unittest.TestCase):
    def analyze(self, records, human=0):
        return analyze(list(enumerate(records, 1)), human, 's', 'source')

    def test_low_counter_hits_special_lows_and_legacy_rates(self):
        records = [event(10, 'block', actor=1, target=0, hit_level='low'),
                   event(20, actor=1, target=0, hit_level='low'),
                   event(30, 'counter_hit', actor=1, target=0, hit_level='low'),
                   event(40, actor=1, target=0, hit_level='special_low')]
        result = self.analyze(records)['low_defense']
        self.assertEqual((result['successes'], result['opportunities'], result['failures']), (1, 3, 2))
        self.assertEqual(result['value'], block(records, 0, Situations([]), None)['low_block_rate'])
        self.assertEqual([item['opportunity']['line'] for item in result['evidence']], [1, 2, 3])

    def test_throw_breaks_do_not_add_attempts_and_slots_are_authoritative(self):
        records = [event(10, 'throw', actor=0, target=1), event(15, 'throw_break', actor=1, target=0),
                   event(20, 'throw', actor=0, target=1)]
        result = self.analyze(records, human=1)['throw_defense']
        self.assertEqual((result['successes'], result['opportunities'], result['value']), (1, 2, .5))
        self.assertEqual(result['evidence'][0]['response']['line'], 2)

    def test_orphan_break_is_visible_and_not_a_clamped_new_rate(self):
        result = self.analyze([event(10, 'throw_break', actor=0, target=1)])['throw_defense']
        self.assertEqual(result['state'], 'invalid')
        self.assertEqual(result['successes'], 1)
        self.assertIsNone(result['failures'])
        self.assertIsNone(result['value'])
        self.assertEqual(result['anomalies'][0]['kind'], 'orphan_throw_break')

    def test_break_from_another_round_does_not_match(self):
        result = self.analyze([event(100, 'throw', actor=1, target=0), event(5, 'throw_break', round_=2, actor=0, target=1)])['throw_defense']
        self.assertEqual(result['state'], 'invalid')

    def test_same_frame_break_cannot_pair_with_a_later_source_record(self):
        result = self.analyze([event(10, 'throw_break', actor=0, target=1), event(10, 'throw', actor=1, target=0)])['throw_defense']
        self.assertEqual(result['state'], 'invalid')

    def test_punish_pairs_one_hit_with_latest_unmatched_opportunity(self):
        records = [event(10, 'block', actor=1, target=0, frame_advantage=-12),
                   event(12, 'block', actor=1, target=0, frame_advantage=-12),
                   event(15, actor=0, target=1), event(16, actor=0, target=1),
                   event(2, 'hit', round_=2, actor=0, target=1)]
        result = self.analyze(records)['punish_conversion']
        self.assertEqual(result['successes'], 2)
        self.assertEqual([row['response']['line'] for row in result['evidence']], [4, 3])
        self.assertEqual(result['value'], block(records, 0, Situations([]), None)['punish_rate'])

    def test_simultaneous_events_have_distinct_provenance(self):
        records = [event(10, actor=1, target=0, hit_level='low') for _ in range(2)]
        result = self.analyze(records)['low_defense']
        self.assertEqual(result['opportunities'], 2)
        self.assertNotEqual(result['evidence'][0]['opportunity'], result['evidence'][1]['opportunity'])

    def test_focus_threshold_ties_override_and_punish_gate(self):
        records = [event(n, actor=1, target=0, hit_level='low') for n in range(1, 5)]
        metrics = self.analyze(records)
        self.assertIsNone(select(metrics)['metric'])
        self.assertEqual(select(metrics, 'low_defense')['mode'], 'manual')
        records.append(event(5, actor=1, target=0, hit_level='low'))
        records += [event(10 + n, 'throw', actor=1, target=0) for n in range(5)]
        metrics = self.analyze(records)
        self.assertEqual(select(metrics)['metric'], 'low_defense')
        metrics['low_defense']['state'] = 'invalid'
        self.assertEqual(select(metrics)['metric'], 'throw_defense')
        with self.assertRaises(ValueError):
            select(metrics, 'low_defense')
        with self.assertRaises(ValueError):
            select(metrics, 'punish_conversion')

    def test_no_opportunities_remain_null(self):
        for metric in self.analyze([]).values():
            self.assertIsNone(metric['value'])
            self.assertEqual(metric['state'], 'no_opportunities')


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ('recordings', 'sessions', 'learning', 'eval', 'reports'):
            (self.root / directory).mkdir()
        self.meta = {'session_id': 's', 'started_at': '2026-10-18T00:00:00Z', 'player': 'test',
                     'human_slot': 0, 'human_character': 'devil_jin', 'bot_character': 'kazuya',
                     'difficulty': 3, 'rounds': [], 'mode': 'versus'}
        self.path = self.root / 'recordings/s.jsonl'
        self.records = [event(n, actor=1, target=0, hit_level='low', damage=10) for n in range(1, 7)] + [summary()]
        self.write_records()
        (self.root / 'sessions/s.json').write_text(json.dumps(self.meta))
        self.learning = {'t': 'learning_round', 'session_id': 's', 'round': 1, 'prediction_accuracy': .6,
                         'habits': {'low_defense': {'n': 5, 'p': .8, 'fixed': False}}}
        (self.root / 'learning/s.jsonl').write_text(json.dumps(self.learning) + '\n')
        self.repository = InsightRepository(self.root)

    def write_records(self):
        self.path.write_text(''.join(json.dumps(record) + '\n' for record in self.records))

    def snapshot(self, **kwargs):
        return self.repository.snapshot('s', **kwargs)

    def test_counts_snapshot_identity_and_bounded_evidence(self):
        result = self.snapshot(limit=2)
        self.assertEqual(result['calculation_version'], 4)
        self.assertEqual(CALCULATION_VERSION, 4)
        self.assertEqual(result['metrics']['low_defense']['opportunities'], 6)
        self.assertEqual(result['metrics']['low_defense']['evidence_total'], 6)
        self.assertEqual(len(result['metrics']['low_defense']['evidence']), 2)
        self.assertEqual(len(result['moments']), 2)
        self.assertEqual(result['moments_total'], 6)
        self.assertEqual(encoded(result), encoded(self.snapshot(limit=2)))
        result['metrics']['low_defense']['successes'] = 99
        self.assertEqual(self.snapshot(limit=2)['metrics']['low_defense']['successes'], 0)

    def test_cache_reuses_derivation_but_detects_same_size_correction(self):
        original = self.snapshot()
        with patch('analytics.insights.recording_records', side_effect=AssertionError('cache missed')):
            self.snapshot()
        before = self.path.stat()
        self.path.write_bytes(self.path.read_bytes().replace(b'"damage": 10', b'"damage": 20', 1))
        os.utime(self.path, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertNotEqual(self.snapshot()['snapshot_id'], original['snapshot_id'])

    def test_open_round_does_not_change_completed_focus_population(self):
        self.records.append(event(1, 'block', round_=2, actor=1, target=0, hit_level='low'))
        self.write_records()
        result = self.snapshot()
        self.assertEqual(result['freshness']['latest_recording_round'], 2)
        self.assertEqual(result['freshness']['completed_rounds'], [1])
        self.assertEqual(result['metrics']['low_defense']['opportunities'], 6)

    def test_blocking_low_and_missing_punish_keep_distinct_moment_outcomes(self):
        self.records[0] = event(1, 'block', actor=1, target=0, hit_level='low', frame_advantage=-12)
        self.write_records()
        moment = next(row for row in self.snapshot()['moments'] if row['reference']['line'] == 1)
        self.assertEqual(moment['outcome'], 'mixed')
        self.assertEqual(moment['metric_outcomes']['low_defense']['outcome'], 'success')
        self.assertEqual(moment['metric_outcomes']['punish_conversion']['outcome'], 'failure')

    def test_source_positions_include_blank_and_unknown_lines(self):
        self.path.write_text('\n' + json.dumps({'t': 'extension'}) + '\n' + self.path.read_text())
        result = self.snapshot()
        self.assertEqual(result['metrics']['low_defense']['evidence'][0]['opportunity']['line'], 3)
        self.assertEqual(result['quality']['unsupported_records'], 1)

    def test_irrelevant_plan_without_round_envelope_does_not_break_insights(self):
        plan = json.loads((ROOT / 'contracts/examples/gameplan.json').read_text())
        plan.update(t='plan', session_id='s')
        self.path.write_text(json.dumps(plan) + '\n' + self.path.read_text())
        result = self.snapshot()
        self.assertEqual(result['metrics']['low_defense']['opportunities'], 6)
        self.assertIsNone(self.repository.resolve('s', result['snapshot_id'], 1))

    def test_partial_recording_tail_and_completed_append(self):
        first = self.snapshot()
        with self.path.open('ab') as stream:
            stream.write(b'{"t":"event","unfinished":"\xe2')
        pending = self.snapshot()
        self.assertTrue(pending['sources']['recording']['pending_tail'])
        self.assertEqual(pending['metrics'], first['metrics'])
        self.write_records()
        self.records += [event(1, round_=2, actor=1, target=0, hit_level='low'), summary(2)]
        self.write_records()
        next_ = self.snapshot()
        self.assertEqual(next_['metrics']['low_defense']['opportunities'], 7)
        self.assertEqual(next_['freshness']['pending_learning_rounds'], [2])

    def test_learning_tail_waits_then_catches_up_and_rejects_complete_bad_line(self):
        path = self.root / 'learning/s.jsonl'
        path.write_bytes(path.read_bytes() + b'{"t":"learning_round","round":')
        self.assertTrue(self.snapshot()['sources']['learning']['pending_tail'])
        path.write_text(json.dumps(self.learning))
        self.assertEqual(self.snapshot()['learning']['prediction_accuracy'][0]['value'], .6)
        path.write_text('{broken}\n')
        with self.assertRaises(DataError):
            self.snapshot()

    def test_learning_utf8_cutoff_waits(self):
        raw, pending = prefix(json.dumps(self.learning).encode() + b'\n{"x":"\xe2')
        self.assertTrue(pending)
        self.assertEqual(raw, json.dumps(self.learning).encode() + b'\n')

    def test_invalid_utf8_is_not_mistaken_for_a_partial_character(self):
        with self.assertRaises(DataError):
            prefix(b'{"x":"\xff')

    def test_same_stamp_metadata_correction_refreshes_capture(self):
        first = self.snapshot()
        path = self.root / 'sessions/s.json'
        before = path.stat()
        path.write_text(path.read_text().replace('"difficulty": 3', '"difficulty": 4'))
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertNotEqual(self.snapshot()['snapshot_id'], first['snapshot_id'])

    def test_unknown_mode_is_not_labelled_measured_real_data(self):
        self.meta.pop('mode')
        (self.root / 'sessions/s.json').write_text(json.dumps(self.meta))
        self.assertIsNone(self.snapshot()['synthetic'])

    def test_invalid_recording_exposes_quality_and_suppresses_focus(self):
        self.path.write_text(self.path.read_text() + 'bad\n')
        result = self.snapshot()
        self.assertEqual(result['quality']['skipped_recording_lines'], 1)
        self.assertEqual(result['metrics']['low_defense']['state'], 'invalid')
        self.assertIsNone(result['focus']['metric'])

    def test_source_replacement_deletion_and_stale_reference(self):
        original = self.snapshot()
        line = original['moments'][0]['reference']['line']
        self.assertEqual(self.repository.resolve('s', original['snapshot_id'], line)['record']['kind'], 'hit')
        replacement = self.path.with_suffix('.replacement')
        replacement.write_text(self.path.read_text() + '\n')
        os.replace(replacement, self.path)
        with self.assertRaisesRegex(DataError, 'Stale'):
            self.repository.resolve('s', original['snapshot_id'], line)
        self.path.unlink()
        with self.assertRaises(DataError):
            self.snapshot()

    def test_snapshot_detects_changes_during_capture(self):
        with patch('analytics.insights.stamp', return_value=('changed',)):
            with self.assertRaises(DataError):
                self.snapshot()

    def test_missing_optional_data_and_invalid_report_do_not_erase_counts(self):
        (self.root / 'learning/s.jsonl').unlink()
        (self.root / 'reports/s.json').write_text('not JSON')
        result = self.snapshot()
        self.assertEqual(result['metrics']['low_defense']['opportunities'], 6)
        self.assertEqual(result['learning']['finetune'], {'before': None, 'after': None})
        self.assertEqual(result['report']['status'], 'invalid')
        self.assertEqual(result['freshness']['pending_learning_rounds'], [1])

    def test_invalid_eval_and_mismatched_learning_fail(self):
        evaluation = self.root / 'eval/s.json'
        evaluation.write_text('{"before": 0.4, "after": 2}')
        with self.assertRaises(DataError):
            self.snapshot()
        evaluation.unlink()
        self.learning['session_id'] = 'different'
        (self.root / 'learning/s.jsonl').write_text(json.dumps(self.learning) + '\n')
        with self.assertRaises(DataError):
            self.snapshot()

    def test_unknown_ids_limits_and_output_path_guards(self):
        self.assertIsNone(self.repository.snapshot('unknown'))
        for sid in ('../s', '/s', 'CON', 's\n', 's/../../other'):
            with self.assertRaises(ValueError):
                check_id(sid)
        for limit in (0, 51, True):
            with self.assertRaises(ValueError):
                self.snapshot(limit=limit)
        with self.assertRaises(ValueError):
            write_export(self.snapshot(), ROOT / 'data/samples/should-not-write')

    def test_atomic_export_and_cli_are_deterministic_and_cloud_independent(self):
        output = self.root / 'analytics'
        result = self.snapshot()
        paths = write_export(result, output)
        first = [Path(path).read_bytes() for path in paths]
        self.assertIn(b'Fine-tune comparison: unavailable', first[1])
        write_export(result, output)
        self.assertEqual(first, [Path(path).read_bytes() for path in paths])
        command = [sys.executable, '-m', 'analytics.insights', 's', '--data-dir', str(self.root)]
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                             env={**os.environ, 'SENTRY_DSN': 'invalid-should-not-initialize', 'DATABASE_URL': 'invalid-should-not-connect'})
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(first, [Path(path).read_bytes() for path in paths])
        self.assertIn('0/6', run.stdout)
        self.assertEqual(list(output.glob('.insights-*')), [])


class RealInsightTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sid = '2026-10-18T05-14-03_sahil_djin_vs_kaz'
        cls.repository = InsightRepository(ROOT / 'data/samples/live_learning')
        cls.body = cls.repository.snapshot(cls.sid)

    def test_independent_source_populations_match_explanation(self):
        metrics = self.body['metrics']
        self.assertEqual([(metrics[key]['successes'], metrics[key]['opportunities']) for key in ('low_defense', 'throw_defense', 'punish_conversion')], [(0, 16), (1, 4), (0, 6)])
        self.assertEqual(self.body['focus']['metric'], 'low_defense')
        self.assertEqual(self.body['quality']['skipped_recording_lines'], 0)
        self.assertFalse(self.body['synthetic'])

    def test_first_fixed_current_regressed_and_estimates_are_separate(self):
        habits = self.body['learning']['habits']
        self.assertEqual(habits['after_block:any']['first_fixed_round'], 2)
        self.assertFalse(habits['after_block:any']['current']['fixed'])
        self.assertTrue(habits['after_block:any']['history'][2]['regressed'])
        self.assertIsNone(habits['low_defense']['first_fixed_round'])
        self.assertEqual(habits['low_defense']['current']['n'], 15)
        self.assertEqual(self.body['tactical']['habit_driven_decisions'], 33)
        self.assertEqual(self.body['learning']['finetune'], {'before': None, 'after': None})

    def test_every_returned_reference_resolves_to_original_source(self):
        path = ROOT / 'data/samples/live_learning/recordings' / f'{self.sid}.jsonl'
        lines = path.read_text().splitlines()
        for metric in self.body['metrics'].values():
            for evidence in metric['evidence']:
                for ref in (evidence['opportunity'], evidence['response']):
                    if ref:
                        original = json.loads(lines[ref['line'] - 1])
                        self.assertEqual((ref['round'], ref['frame']), (original['round'], original['frame']))


if __name__ == '__main__':
    unittest.main()
