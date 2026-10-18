import json
import unittest

from analytics.insight_examples import FIXTURES, PUBLIC_FIXTURES, build_examples, serialized_examples, serialized_public
from analytics.insights import PUBLIC_VALIDATOR, SNAPSHOT_VALIDATOR, public


class InsightExamplesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.examples = build_examples()

    def test_examples_match_schema_and_keep_counts_independent_of_limits(self):
        for name, value in self.examples.items():
            with self.subTest(name=name):
                SNAPSHOT_VALIDATOR.validate(value)
                self.assertLessEqual(len(value['moments']), 5)
                self.assertTrue(all(len(m['evidence']) <= 3 for m in value['metrics'].values()))
        real = self.examples['real']
        self.assertFalse(real['synthetic'])
        self.assertEqual([(m['successes'], m['opportunities']) for m in real['metrics'].values()], [(0, 16), (1, 4), (0, 6)])
        self.assertEqual(real['focus']['metric'], 'low_defense')
        self.assertTrue(self.examples['synthetic']['synthetic'])

    def test_edge_examples_expose_distinct_display_states(self):
        values = self.examples
        self.assertEqual(values['early_signal']['metrics']['low_defense']['state'], 'early_signal')
        self.assertIsNone(values['early_signal']['focus']['metric'])
        self.assertEqual(values['no_opportunities']['metrics']['low_defense']['state'], 'no_opportunities')
        self.assertIsNone(values['no_opportunities']['metrics']['low_defense']['value'])
        self.assertEqual(values['invalid_recording']['quality']['state'], 'invalid')
        self.assertIsNone(values['invalid_recording']['focus']['metric'])
        self.assertEqual(values['orphan_break']['metrics']['throw_defense']['state'], 'invalid')
        self.assertEqual(values['manual_focus']['focus']['mode'], 'manual')
        self.assertEqual(values['manual_focus']['focus']['metric'], 'throw_defense')
        self.assertEqual(values['pending_learning']['freshness']['pending_learning_rounds'], [2])
        self.assertEqual(values['current_learning']['freshness']['pending_learning_rounds'], [])
        self.assertNotEqual(values['pending_learning']['snapshot_id'], values['current_learning']['snapshot_id'])
        self.assertEqual(values['mixed_outcomes']['moments'][0]['outcome'], 'mixed')
        self.assertEqual(values['observed']['report']['status'], 'unavailable')
        for name, value in values.items():
            if name != 'real':
                self.assertTrue(value['synthetic'], name)
            if value['focus']['action']:
                self.assertEqual(value['focus']['action_status'], 'draft_awaiting_Garrett_review')

    def test_public_views_keep_counts_states_and_focus(self):
        for name, value in self.examples.items():
            with self.subTest(name=name):
                view = public(value)
                PUBLIC_VALIDATOR.validate(view)
                self.assertEqual(view['snapshot_id'], value['snapshot_id'])
                self.assertEqual(view['recording_sha256'], value['sources']['recording']['sha256'])
                self.assertEqual(view['quality'], value['quality']['state'])
                self.assertEqual(view['focus']['metric'], value['focus']['metric'])
                self.assertFalse(view['focus']['action_reviewed'])
                for key, metric in value['metrics'].items():
                    self.assertEqual((view['metrics'][key]['successes'], view['metrics'][key]['opportunities'], view['metrics'][key]['state']),
                                     (metric['successes'], metric['opportunities'], metric['state']))
                    self.assertTrue(all('kind' in item['event'] for item in view['metrics'][key]['evidence']))
        real = public(self.examples['real'])
        self.assertEqual(real['freshness']['latest_completed_round'], 4)
        self.assertEqual(real['habits']['after_block:any'], {'first_detected_round': 2, 'first_fixed_round': 2, 'current_round': 4,
                                                             'fixed': False, 'regressed': False, 'last_regressed_round': 3})
        self.assertIsNone(real['habits']['low_defense']['first_fixed_round'])
        self.assertEqual(real['metrics']['low_defense']['evidence'][0]['event']['hit_level'], 'low')
        mixed = public(self.examples['mixed_outcomes'])['moments'][0]
        self.assertEqual(mixed['outcome'], 'mixed')
        self.assertEqual({k: v['outcome'] for k, v in mixed['metric_outcomes'].items()}, {'low_defense': 'success', 'punish_conversion': 'failure'})
        self.assertEqual(public(self.examples['pending_learning'])['quality'], 'pending')

    def test_committed_public_fixtures_have_no_drift(self):
        expected = serialized_public(self.examples)
        self.assertEqual({p.name for p in PUBLIC_FIXTURES.glob('*.json')}, set(expected))
        for name, content in expected.items():
            with self.subTest(name=name):
                self.assertEqual((PUBLIC_FIXTURES / name).read_text(encoding='utf-8'), content)

    def test_committed_fixtures_have_no_drift(self):
        expected = serialized_examples()
        self.assertEqual({p.name for p in FIXTURES.glob('*.json')}, set(expected))
        for name, content in expected.items():
            with self.subTest(name=name):
                self.assertEqual((FIXTURES / name).read_text(encoding='utf-8'), content)
                self.assertEqual(json.loads(content), self.examples[name.removesuffix('.json')])


if __name__ == '__main__':
    unittest.main()
