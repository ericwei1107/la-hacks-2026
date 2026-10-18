import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/samples/live_learning'
SID = '2026-10-18T05-14-03_sahil_djin_vs_kaz'


def start(args):
    return subprocess.Popen([sys.executable, *args], cwd=ROOT, env={**os.environ, 'DATA_DIR': str(DATA), 'SENTRY_DSN': '', 'DATABASE_URL': ''}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def ready(processes):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        for process in processes:
            if process.poll() is not None:
                raise AssertionError(process.communicate()[0])
        try:
            for port, name in ((8765, 'brain'), (8766, 'replay'), (8767, 'analytics')):
                response = httpx.get(f'http://127.0.0.1:{port}/health', timeout=1)
                response.raise_for_status()
                assert response.json()['service'] == name
            return
        except (httpx.HTTPError, ValueError):
            time.sleep(0.1)
    raise AssertionError('Live sample services did not become ready')


async def streams():
    async with websockets.connect('ws://127.0.0.1:8765/ws/state') as state, websockets.connect('ws://127.0.0.1:8765/ws/coach') as coach:
        record = json.loads(await asyncio.wait_for(state.recv(), 5))
        assert record['session_id'] == SID
        async with asyncio.timeout(10):
            while True:
                summary = json.loads(await coach.recv())
                if summary['t'] == 'round_summary':
                    assert summary['session_id'] == SID
                    assert 'low_defense' not in summary['newly_fixed']
                    return


def run():
    processes = []
    try:
        processes.append(start(['tools/mock/serve.py', '--services', 'brain,replay', '--rate', '600']))
        processes.append(start(['-m', 'uvicorn', 'analytics.main:app', '--host', '127.0.0.1', '--port', '8767', '--log-level', 'warning']))
        ready(processes)
        with httpx.Client(base_url='http://127.0.0.1:8767', timeout=20) as client:
            response = client.get(f'/learning/{SID}')
            response.raise_for_status()
            metrics = response.json()
            assert [r['prediction_accuracy'] for r in metrics['rounds']] == [0.6, 0.7333, 0.9048, 1.0]
            assert metrics['time_to_detect']['low_defense'] == 3
            assert metrics['time_to_mastery'] == {'after_block:any': 2}
            assert metrics['finetune'] == {'before': None, 'after': None}
            response = client.get(f'/stats/{SID}')
            response.raise_for_status()
            stats = response.json()
            assert stats['totals']['low_block_rate'] == 0
            assert stats['totals']['rounds_won'] == 1
            assert stats['skipped_lines'] == 0
            response = client.get('/trends/sahil/devil_jin')
            response.raise_for_status()
            values = response.json()['series'][0]['values']
            assert values['win_rate:difficulty:3'] == 0.25
            assert 'time_to_mastery:low_defense' not in values
            assert values['time_to_mastery:after_block:any'] == 2
        sessions = httpx.get('http://127.0.0.1:8765/sessions', timeout=20).json()
        assert any(s['session_id'] == SID and s['mode'] == 'versus' for s in sessions)
        asyncio.run(streams())
        print('PASS: real live-learning sample; stats/learning/trends, brain catalogue and both WebSockets; no low_defense mastery fabricated')
    finally:
        for process in processes:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
        for process in processes:
            try:
                output = process.communicate(timeout=10)[0]
            except subprocess.TimeoutExpired:
                process.kill()
                output = process.communicate()[0]
                raise AssertionError(f'Live sample shutdown timed out: {output}')
            assert process.returncode == 0, output
    print('PASS: all local test services shut down; no Sentry telemetry or cloud upload')


if __name__ == '__main__':
    run()
