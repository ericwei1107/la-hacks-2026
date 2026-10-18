import asyncio
import copy
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import analytics
import brain
import replay
from store import ROOT, Session, Store, check, load_jsonl

FIXTURE = Path(__file__).parent / "fixtures" / "two-rounds.jsonl"


class BoundariesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"DATA_DIR": self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.store = Store([FIXTURE])
        self.session = self.store.default()
        self.sid = self.session.id

    def test_metadata_missing_fails(self):
        path = self.directory / "missing.jsonl"
        path.write_text(FIXTURE.read_text())
        with self.assertRaisesRegex(ValueError, "missing metadata"):
            Store([path])

    def test_metadata_index_and_explicit_selection(self):
        directory = self.directory / "sessions"
        directory.mkdir()
        meta = copy.deepcopy(self.session.meta)
        meta["recording"] = str(FIXTURE.resolve())
        (directory / "indexed.json").write_text(json.dumps(meta))
        store = Store([ROOT / "data/samples/practice_djin_vs_kaz.jsonl"])
        self.assertIn(self.sid, store.sessions)
        self.assertNotEqual(store.default().id, self.sid)
        self.assertEqual(self.session.meta["player"], "fixture")

    def test_metadata_id_mismatch_fails(self):
        path = self.directory / "bad.jsonl"
        path.write_text(FIXTURE.read_text())
        meta = copy.deepcopy(self.session.meta)
        meta["session_id"] = "wrong"
        path.with_suffix(".session.json").write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, "does not match"):
            Session(path)

    def test_malformed_complete_lines_fail(self):
        path = self.directory / "broken.jsonl"
        for text in ('{"t":\n', '{"t":\n{}\n', 'not JSON'):
            path.write_text(text)
            with self.assertRaisesRegex(ValueError, "broken.jsonl:1"):
                load_jsonl(path)

    def test_optional_files_and_config_rollback(self):
        with TestClient(brain.create(self.store)) as client:
            self.assertEqual(client.get('/profiles/fixture').json(), [])
            self.assertEqual(client.get('/config').json()['player'], 'fixture')
            before = client.get('/config').json()
            self.assertEqual(client.post('/config', json={'knobs': {'exploit_weight': 9}}).status_code, 422)
            self.assertEqual(client.get('/config').json(), before)
            self.assertEqual(client.post('/config', content='{').status_code, 422)
            response = client.options('/config', headers={'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'POST'})
            self.assertEqual(response.headers['access-control-allow-origin'], '*')
            self.assertEqual(set(client.get('/health').json()), {'ok', 'service', 'version'})

    def test_saved_report_checks_loaded_session(self):
        with TestClient(replay.create(self.store)) as client:
            self.assertEqual(client.get(f'/reports/{self.sid}').status_code, 404)
            report = client.post(f'/analyze/{self.sid}').json()
            self.assertEqual(check('report', report), [])
            valid = {(r['round'], r['frame']) for r in self.session.records if 'frame' in r}
            for item in report['decision_points']:
                self.assertIn((item['round'], item['frame']), valid)
            self.assertEqual(client.get('/reports/unknown').status_code, 404)
            self.assertEqual(client.post('/analyze/unknown').status_code, 404)
            self.assertEqual(client.post('/coach/round', content='{').status_code, 422)
        with TestClient(replay.create(self.store)) as client:
            self.assertEqual(client.get(f'/reports/{self.sid}').json(), report)

    def test_learning_and_filtered_trends(self):
        with TestClient(analytics.create(self.store)) as client:
            metrics = client.get(f'/learning/{self.sid}').json()
            self.assertEqual(check('metrics', metrics), [])
            self.assertEqual(len(metrics['rounds']), 2)
            self.assertEqual(client.get('/trends/missing/devil_jin').json()['series'], [])
            series = client.get('/trends/fixture/devil_jin?stat=low_block_rate').json()['series']
            self.assertEqual(set(series[0]['values']), {'low_block_rate'})
            self.assertEqual(client.get('/stats/unknown').status_code, 404)

    def test_long_habit_coach_is_under_40_words(self):
        summary = json.loads((ROOT/'contracts/examples/round_summary.json').read_text())
        summary['top_habits'][0]['situation'] = 'word ' * 100
        with TestClient(replay.create(self.store)) as client:
            response = client.post('/coach/round', json=summary)
            self.assertLess(len(response.json()['text'].split()), 40)
            summary['newly_fixed'] = ['word ' * 100]
            response = client.post('/coach/round', json=summary)
            self.assertLess(len(response.json()['text'].split()), 40)

    def test_profiles_loaded_and_missing_learning_empty(self):
        profile = json.loads((ROOT/'contracts/examples/profile.json').read_text())
        profile['player'] = 'fixture'
        directory = self.directory / 'profiles'
        directory.mkdir()
        (directory/'profile.json').write_text(json.dumps(profile))
        with TestClient(brain.create(self.store)) as client:
            loaded = client.get('/profiles/fixture').json()
            self.assertEqual(loaded, [profile])
            self.assertEqual(check('profile', loaded[0]), [])
            self.assertEqual(client.get('/profiles/other').json(), [])
        real = Store([ROOT/'data/samples/practice_djin_vs_kaz.jsonl'])
        with TestClient(analytics.create(real)) as client:
            metrics = client.get(f'/learning/{real.default().id}').json()
            self.assertEqual(metrics['rounds'], [])
            self.assertEqual(metrics['finetune'], {'before': None, 'after': None})

    def test_no_loop_late_connection_and_unknown_session_close(self):
        with TestClient(brain.create(self.store, rate=600, loop=False)) as client:
            time.sleep(0.05)
            with client.websocket_connect('/ws/state') as stream:
                with self.assertRaises(WebSocketDisconnect) as closed:
                    stream.receive_json()
                self.assertEqual(closed.exception.code, 1000)
            with client.websocket_connect('/ws/state?session=unknown') as stream:
                with self.assertRaises(WebSocketDisconnect) as closed:
                    stream.receive_json()
                self.assertEqual(closed.exception.code, 1008)

    def test_websockets_rounds_and_loop(self):
        with TestClient(brain.create(self.store, rate=60)) as client:
            with client.websocket_connect('/ws/coach') as coach:
                summaries = []
                while len(summaries) < 3:
                    item = coach.receive_json()
                    if item['t'] == 'round_summary':
                        self.assertEqual(check('round_summary', item), [])
                        summaries.append(item['round'])
                    else:
                        self.assertEqual(item['t'], 'coach')
                self.assertEqual(summaries[0], summaries[2])
                self.assertNotEqual(summaries[0], summaries[1])
            with client.websocket_connect('/ws/state') as state:
                for _ in range(12):
                    record = state.receive_json()
                    self.assertIn(record['t'], ('state', 'event'))
                    if record['t'] == 'state':
                        self.assertEqual(record['future_field'], 'preserved')


class TimelineTest(unittest.IsolatedAsyncioTestCase):
    async def test_round_reset_loop_and_frame_gaps(self):
        session = Session(FIXTURE)
        timeline = brain.Timeline(session, rate=60)
        self.assertEqual(timeline.items[0][0], 0)
        self.assertEqual(timeline.total, 6)
        seen, now = [], [0.0]

        async def sleep(delay):
            now[0] += delay

        def publish(channel, record):
            seen.append((now[0], channel, record))
            if len(seen) == len(timeline.items) * 2:
                raise StopAsyncIteration

        with self.assertRaises(StopAsyncIteration):
            await timeline.play(publish, monotonic=lambda: now[0], sleep=sleep)
        self.assertAlmostEqual(seen[len(timeline.items)][0], 6/60)
        self.assertEqual([r['kind'] for _, c, r in seen if c == 'state' and r['t'] == 'event'], ['round_start','round_end','round_start','round_end'] * 2)
        self.assertAlmostEqual(seen[2][0], 2/60)
        session.records[2]['frame'] += 300
        long = brain.Timeline(session)
        self.assertGreater(long.total, 300)

    async def test_slow_clients_do_not_drop_required_records(self):
        broadcast = brain.Broadcast(capacity=1)
        slow = broadcast.subscribe('state')
        fast = broadcast.subscribe('state')
        broadcast.publish('state', {'t':'state'})
        await fast.get()
        broadcast.publish('state', {'t':'state'})
        self.assertEqual(slow.qsize(), 1)
        await fast.get()
        broadcast.publish('state', {'t':'event','kind':'round_end'})
        self.assertIsNone(await slow.get())
        self.assertNotIn(slow, broadcast.subscribers['state'])
        self.assertEqual((await fast.get())['t'], 'event')

    async def test_no_loop_publishes_once(self):
        seen = []
        now = [0.0]

        async def sleep(delay):
            now[0] += delay

        timeline = brain.Timeline(Session(FIXTURE))
        await timeline.play(lambda channel, record: seen.append(record), loop=False, monotonic=lambda: now[0], sleep=sleep)
        self.assertEqual(len(seen), len(timeline.items))
        self.assertAlmostEqual(now[0], timeline.total/60)
