import json
import os
import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

os.environ['SENTRY_DSN'] = ''

from fastapi.testclient import TestClient

from analytics.main import create_app
from analytics.repository import ROOT, FileRepository, VALIDATORS
from analytics.tigerdata.source import prepare
from analytics.tigerdata.trends import snapshot

DATA = ROOT / 'data/samples/live_learning'
SID = '2026-10-18T05-14-03_sahil_djin_vs_kaz'


class LiveLearningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = DATA / 'recordings' / f'{SID}.jsonl'
        cls.records = [json.loads(line) for line in cls.path.read_text().splitlines() if line.strip()]
        cls.meta = json.loads((DATA / 'sessions' / f'{SID}.json').read_text())
        cls.files = FileRepository(DATA)
        with patch.dict(os.environ, {'DATABASE_URL': ''}):
            cls.client = TestClient(create_app(DATA))
        cls.bodies = {}
        for name, route in [('stats', f'/stats/{SID}'), ('learning', f'/learning/{SID}'), ('trends', '/trends/sahil/devil_jin')]:
            response = cls.client.get(route)
            if response.status_code != 200:
                raise AssertionError((route, response.status_code, response.text))
            cls.bodies[name] = response.json()

    def test_measured_learning_and_first_mastery_survive_regression(self):
        body = self.bodies['learning']
        self.assertEqual(list(VALIDATORS['metrics'].iter_errors(body)), [])
        self.assertEqual([r['prediction_accuracy'] for r in body['rounds']], [0.6, 0.7333, 0.9048, 1.0])
        self.assertEqual(body['time_to_detect']['low_defense'], 3)
        self.assertEqual(body['time_to_mastery'], {'after_block:any': 2})
        self.assertTrue(body['rounds'][1]['habits']['after_block:any']['fixed'])
        self.assertFalse(body['rounds'][2]['habits']['after_block:any']['fixed'])
        self.assertFalse(body['rounds'][3]['habits']['low_defense']['fixed'])
        self.assertEqual(body['rounds'][3]['habits']['low_defense']['n'], 15)
        self.assertEqual(body['finetune'], {'before': None, 'after': None})

    def test_recorded_events_are_after_block_transitions_not_low_mastery(self):
        events = [r for r in self.records if r['t'] == 'learning_event']
        self.assertEqual([(r['event'], r['situation'], r['round'], r['frame']) for r in events], [('fixed', 'after_block:any', 2, 1804), ('regressed', 'after_block:any', 3, 342)])
        summaries = [r for r in self.records if r['t'] == 'round_summary']
        self.assertEqual(len(summaries), 4)
        self.assertEqual(summaries[1]['newly_fixed'], ['after_block:any'])
        self.assertEqual(summaries[2]['regressed'], ['after_block:any'])
        self.assertFalse(any('low_defense' in r['newly_fixed'] for r in summaries))

    def test_observed_lows_and_exploitation_are_separate_from_estimates(self):
        counts = Counter(r['t'] for r in self.records)
        self.assertEqual(counts['state'], 10080)
        self.assertEqual(counts['event'], 238)
        tactical = [r for r in self.records if r['t'] == 'tactical']
        self.assertEqual(len(tactical), 351)
        self.assertEqual(sum(r['source'] != 'reflex' for r in tactical), 231)
        self.assertEqual(sum(r['source'] == 'habit' for r in tactical), 33)
        self.assertEqual([sum(r['round'] == n and r['chosen'] == 'low' for r in tactical) for n in range(1, 5)], [6, 8, 8, 17])
        self.assertEqual(sum(r['round'] == 4 and r['chosen'] == 'low' and r['source'] == 'habit' for r in tactical), 17)
        lows = [r for r in self.records if r['t'] == 'event' and r['kind'] in ('block', 'hit', 'counter_hit') and r.get('actor') == 1 and r.get('target') == 0 and r.get('hit_level') == 'low']
        self.assertEqual(len(lows), 16)
        self.assertFalse(any(r['kind'] == 'block' for r in lows))
        self.assertEqual(self.bodies['stats']['totals']['low_block_rate'], 0)
        self.assertEqual(self.bodies['stats']['totals']['rounds_won'], 1)
        self.assertEqual(self.bodies['stats']['skipped_lines'], 0)

    def test_completed_round_batches_and_trends_match_measured_stats(self):
        batches = prepare(self.meta, self.path, DATA)
        self.assertEqual([b.number for b in batches], [1, 2, 3, 4])
        kinds = Counter(row.record['t'] for batch in batches for row in batch.rows['round_metrics'])
        self.assertEqual(kinds, {'round_summary': 4, 'learning_round': 4, 'calculated_round': 4})
        derived = snapshot(DATA, self.meta, self.path, batches)
        self.assertTrue(derived.eligible)
        values = {r[3]: r[4] for r in derived.rows if r[2] == 4}
        self.assertEqual(values, self.bodies['trends']['series'][0]['values'])
        self.assertEqual(values['time_to_mastery:after_block:any'], 2)
        self.assertNotIn('time_to_mastery:low_defense', values)
        self.assertEqual(values['win_rate:difficulty:3'], 0.25)

    def test_mock_http_uses_the_same_real_learning_and_stats(self):
        sys.path.insert(0, str(ROOT / 'tools/mock'))
        from analytics_mock import create
        from store import Store
        with patch.dict(os.environ, {'DATA_DIR': str(DATA)}):
            client = TestClient(create(Store([self.path])))
            for name, route in [('stats', f'/stats/{SID}'), ('learning', f'/learning/{SID}'), ('trends', '/trends/sahil/devil_jin')]:
                response = client.get(route)
                self.assertEqual(response.status_code, 200, response.text)
                actual = response.json()
                expected = self.bodies[name].copy()
                if name == 'stats':
                    expected.pop('skipped_lines')
                self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
