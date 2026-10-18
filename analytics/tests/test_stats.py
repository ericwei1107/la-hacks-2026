import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['SENTRY_DSN'] = ''

from fastapi.testclient import TestClient
from analytics.main import create_app
from analytics.repository import ROOT
from analytics.stats import compute

CONTRACT_KEYS = ('damage_taken_by_situation', 'punish_rate', 'throw_break_rate', 'low_block_rate', 'counter_hits_taken', 'counter_hits_given', 'avg_adv_after_block')
SYNTH = '2026-10-17T13-05-00_synth_djin_vs_kaz'
META = {'human_slot': 0, 'rounds': []}


def ev(frame, kind, round_=1, **fields):
    return {'t': 'event', 'session_id': 's', 'round': round_, 'frame': frame, 'kind': kind, **fields}


def state(frame, situation, round_=1, hp=(190, 190)):
    players = [{'health': hp[0]}, {'health': hp[1]}]
    return {'t': 'state', 'session_id': 's', 'round': round_, 'frame': frame, 'players': players, 'derived': {'situation': situation}}


class ComputeTest(unittest.TestCase):
    def totals(self, records, meta=META):
        return compute('s', meta, records)['totals']

    def test_punish_window(self):
        opp = ev(10, 'block', actor=1, target=0, frame_advantage=-12)
        self.assertEqual(self.totals([opp, ev(18, 'hit', actor=0, target=1)])['punish_rate'], 1.0)
        self.assertEqual(self.totals([opp, ev(50, 'hit', actor=0, target=1)])['punish_rate'], 0.0)
        self.assertIsNone(self.totals([ev(10, 'block', actor=1, target=0, frame_advantage=-5)])['punish_rate'])

    def test_throws_follow_the_real_tracker(self):
        records = [ev(10, 'throw', actor=1, target=0), ev(40, 'throw', actor=1, target=0), ev(48, 'throw_break', actor=0, target=1, detail={'input': 'press_1'})]
        body = self.totals(records)
        self.assertEqual(body['throw_break_rate'], 0.5)
        self.assertEqual(body['throw_breaks_by_type'], {'press_1': 1})
        self.assertIsNone(self.totals([])['throw_break_rate'])

    def test_low_block_rate(self):
        lows = [ev(10, 'block', actor=1, target=0, hit_level='low')] + [ev(20 + i, 'hit', actor=1, target=0, hit_level='low') for i in range(3)]
        self.assertEqual(self.totals(lows)['low_block_rate'], 0.25)
        special = [ev(40, 'block', actor=1, target=0, hit_level='special_low'), ev(50, 'hit', actor=1, target=0, hit_level='special_low')]
        self.assertEqual(self.totals(lows + special)['low_block_rate'], 0.25)
        self.assertIsNone(self.totals(special)['low_block_rate'])

    def test_advantage_from_the_human_side(self):
        body = self.totals([ev(10, 'block', actor=1, target=0, frame_advantage=-7), ev(30, 'block', actor=1, target=0, frame_advantage=-3)])
        self.assertEqual(body['avg_adv_after_block'], 5.0)

    def test_situation_falls_back_to_state(self):
        records = [state(5, 'defense'), state(9, 'pressure'), ev(8, 'hit', actor=1, target=0, damage=10), ev(9, 'hit', actor=1, target=0, damage=4, situation='low_defense')]
        self.assertEqual(self.totals(records)['damage_taken_by_situation'], {'defense': 10, 'low_defense': 4})
        self.assertEqual(self.totals([ev(1, 'hit', actor=1, target=0, damage=3)])['damage_taken_by_situation'], {'neutral': 3})

    def test_rounds_won_and_timeline(self):
        records = [state(0, 'neutral', 1), state(30, 'neutral', 1, (150, 190)), state(45, 'neutral', 1, (140, 190)), ev(45, 'round_end', 1, detail={'winner': 1}), state(0, 'neutral', 2), ev(20, 'round_end', 2, detail={'winner': 0})]
        body = compute('s', META, records)
        self.assertEqual([r['rounds_won'] for r in body['rounds']], [0, 1])
        self.assertEqual(body['totals']['rounds_won'], 1)
        self.assertEqual(body['health_timeline']['1'], [[0, 190, 190], [30, 150, 190], [45, 140, 190]])

    def test_contract_shape(self):
        body = compute('s', META, [ev(10, 'hit', actor=1, target=0, damage=5)])
        for block in body['rounds'] + [body['totals']]:
            for key in CONTRACT_KEYS:
                self.assertIn(key, block)
            for key in ('punish_rate', 'throw_break_rate', 'low_block_rate'):
                self.assertTrue(block[key] is None or 0 <= block[key] <= 1)

    def test_real_sample(self):
        path = ROOT / 'data' / 'samples' / 'practice_djin_vs_kaz.jsonl'
        meta = json.loads(path.with_name('practice_djin_vs_kaz.session.json').read_text())
        records = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        body = compute(meta['session_id'], meta, records)
        self.assertIsNone(body['rounds'][0]['rounds_won'])
        self.assertIsNone(body['totals']['low_block_rate'])


class StatsRouteTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run([sys.executable, str(ROOT / 'tools/mock/synth.py'), '--out', str(self.root)], check=True, capture_output=True)
        patcher = patch.dict(os.environ, {'DATABASE_URL': ''})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(create_app(self.root))
        self.recording = self.root / 'recordings' / f'{SYNTH}.jsonl'

    def get(self, sid=SYNTH):
        response = self.client.get(f'/stats/{sid}')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_synthetic_numbers(self):
        body = self.get()
        rounds = body['rounds']
        self.assertEqual([r['low_block_rate'] for r in rounds], [0.2, 0.4, 1.0])
        self.assertEqual([r['throw_break_rate'] for r in rounds], [0.5, None, 1.0])
        self.assertEqual([r['punish_rate'] for r in rounds], [1.0, 1.0, 1.0])
        self.assertEqual([r['rounds_won'] for r in rounds], [0, 0, 1])
        self.assertEqual(rounds[0]['damage_taken_by_situation'], {'low_defense': 48, 'throw_break': 35})
        self.assertEqual(body['totals']['throw_break_rate'], 0.667)
        self.assertEqual(set(body['health_timeline']), {'1', '2', '3'})
        self.assertEqual(body['skipped_lines'], 0)

    def test_unknown_session(self):
        self.assertEqual(self.client.get('/stats/nope').status_code, 404)
        self.assertEqual(self.client.get('/stats/..').status_code, 404)

    def test_live_append_reads_only_new_lines(self):
        before = self.get()['totals']['counter_hits_taken']
        repo = self.client.app.state.repository
        generation = next(iter(repo.tails.values())).generation
        hit = ev(1700, 'counter_hit', 3, actor=1, target=0, damage=9)
        hit['session_id'] = SYNTH
        with open(self.recording, 'a') as f:
            f.write(json.dumps(hit) + '\n' + json.dumps(hit)[:20])
        body = self.get()
        self.assertEqual(body['totals']['counter_hits_taken'], before + 1)
        tail = next(iter(repo.tails.values()))
        self.assertEqual(tail.generation, generation)
        with open(self.recording, 'a') as f:
            f.write(json.dumps(hit)[20:] + '\n')
        self.assertEqual(self.get()['totals']['counter_hits_taken'], before + 2)

    def test_bad_live_line_is_skipped_not_fatal(self):
        with open(self.recording, 'a') as f:
            f.write('{"t": "event", broken\n')
        body = self.get()
        self.assertEqual(body['skipped_lines'], 1)
        self.assertEqual(body['rounds'][0]['low_block_rate'], 0.2)

    def test_rewritten_file_is_reparsed(self):
        self.get()
        lines = self.recording.read_text().splitlines()
        self.recording.write_text('\n'.join(lines[:100]) + '\n')
        body = self.get()
        self.assertEqual(len(body['rounds']), 1)
        self.assertGreater(next(iter(self.client.app.state.repository.tails.values())).generation, 0)


if __name__ == '__main__':
    unittest.main()
