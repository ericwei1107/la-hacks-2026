import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['SENTRY_DSN'] = ''

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import brain
import serve
from live import LiveWriter
from store import ROOT, Store
from analytics.insights import InsightRepository

SYNTHETIC = ROOT / 'data' / 'samples' / 'synthetic'


def lines(path):
    return [json.loads(row) for row in path.read_text(encoding='utf-8').splitlines()]


class LiveWriterTest(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(os.environ, {'DATA_DIR': str(SYNTHETIC)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = Store()
        self.session = self.store.default()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.live = Path(temporary.name) / 'live'

    def test_records_summaries_once_and_learning_after_summary(self):
        writer = LiveWriter(self.session, self.live, learning_delay=0)
        meta = json.loads((self.live / 'sessions' / f'{self.session.id}.json').read_text())
        self.assertEqual(meta['rounds'], [])
        self.assertNotIn('recording', meta)
        self.assertNotIn('ended_at', meta)
        state = next(r for r in self.session.stream() if r['t'] == 'state')
        summary = next(r for r in self.session.records if r['t'] == 'round_summary')
        writer.record('state', state)
        writer.record('coach', summary)
        writer.record('coach', summary)
        writer.record('coach', {'t': 'coach', 'session_id': self.session.id, 'round': 1, 'text': 'x', 'severity': 'info'})
        writer.record('state', brain.DROP)
        recorded = lines(writer.recording)
        self.assertEqual([r['t'] for r in recorded], ['state', 'round_summary'])
        self.assertEqual([r['round'] for r in lines(writer.learning_path)], [summary['round']])
        self.assertTrue(writer.recording.read_bytes().endswith(b'\n'))

    def test_buffers_records_and_flushes_once_per_second_or_at_round_end(self):
        now = [0.0]
        writer = LiveWriter(self.session, self.live, learning_delay=0, clock=lambda: now[0])
        states = [r for r in self.session.stream() if r['t'] == 'state'][:3]
        writer.record('state', states[0])
        writer.record('state', states[1])
        self.assertEqual(writer.recording.read_bytes(), b'')
        now[0] = 1.0
        writer.record('state', states[2])
        self.assertEqual(len(lines(writer.recording)), 3)
        writer.record('state', states[0])
        writer.record('coach', next(r for r in self.session.records if r['t'] == 'round_summary'))
        self.assertEqual([r['t'] for r in lines(writer.recording)][-2:], ['state', 'round_summary'])

    def test_refuses_to_write_into_checked_in_samples(self):
        with self.assertRaises(ValueError):
            LiveWriter(self.session, SYNTHETIC)
        with self.assertRaises(ValueError):
            LiveWriter(self.session, ROOT / 'data' / 'samples' / 'scratch')
        with self.assertRaises(ValueError):
            LiveWriter(self.session, self.live, learning_delay=-1)

    def test_brain_playback_grows_a_folder_the_insight_builder_reads(self):
        writer = LiveWriter(self.session, self.live, learning_delay=.2)
        rate = max(1, brain.Timeline(self.session, 60).total // 2)
        app = brain.create(self.store, rate=rate, loop=False, observer=writer, duplicate_summaries=True)
        summaries = []
        with TestClient(app) as client:
            with client.websocket_connect('/ws/coach') as ws:
                try:
                    while True:
                        record = json.loads(ws.receive_text())
                        if record['t'] == 'round_summary':
                            summaries.append(record['round'])
                except WebSocketDisconnect:
                    pass
            deadline = time.monotonic() + 5
            while len(lines(writer.learning_path)) < len(writer.learning) and time.monotonic() < deadline:
                time.sleep(.05)
        rounds = sorted(set(summaries))
        self.assertTrue(rounds)
        self.assertTrue(all(summaries.count(n) == 2 for n in rounds), summaries)
        recorded = lines(writer.recording)
        self.assertEqual(sorted(r['round'] for r in recorded if r['t'] == 'round_summary'), sorted(writer.learning))
        self.assertEqual(sum(r['t'] in ('state', 'event') for r in recorded), sum(r['t'] in ('state', 'event') for r in self.session.stream()))
        live = InsightRepository(self.live).snapshot(self.session.id, 5)
        source = InsightRepository(SYNTHETIC).snapshot(self.session.id, 5)
        self.assertEqual(live['freshness']['completed_rounds'], source['freshness']['completed_rounds'])
        self.assertEqual(live['freshness']['pending_learning_rounds'], [])
        counts = lambda value: {k: (m['successes'], m['opportunities'], m['state']) for k, m in value['metrics'].items()}
        self.assertEqual(counts(live), counts(source))

    def test_drop_after_coach_closes_sockets_for_reconnect(self):
        rate = max(1, brain.Timeline(self.session, 60).total // 2)
        app = brain.create(self.store, rate=rate, loop=False, drop_after_coach=True)
        with TestClient(app) as client:
            with client.websocket_connect('/ws/coach') as ws:
                self.assertEqual(json.loads(ws.receive_text())['t'], 'round_summary')
                self.assertEqual(json.loads(ws.receive_text())['t'], 'coach')
                with self.assertRaises(WebSocketDisconnect) as closed:
                    ws.receive_text()
        self.assertEqual(closed.exception.code, 1013)


class LiveArgumentsTest(unittest.TestCase):
    def test_live_dir_requires_real_analytics_and_bounded_delay(self):
        with redirect_stderr(io.StringIO()):
            for argv in (['--live-dir', 'x'], ['--live-dir', 'x', '--services', 'replay'], ['--learning-delay', '-1'], ['--learning-delay', '121']):
                with self.subTest(argv=argv), self.assertRaises(SystemExit):
                    serve.parse(argv)
        args = serve.parse(['--live-dir', 'x', '--services', 'brain,replay', '--learning-delay', '0', '--duplicate-summaries', '--drop-after-summary'])
        self.assertEqual((args.live_dir, args.learning_delay, args.duplicate_summaries, args.drop_after_summary), ('x', 0, True, True))


if __name__ == '__main__':
    unittest.main()
