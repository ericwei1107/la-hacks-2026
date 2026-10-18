import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "data/samples/practice_djin_vs_kaz.jsonl"


def start(directory, *flags, recording=SAMPLE):
    selection = ['--recording', str(recording)] if recording is not None else []
    return subprocess.Popen(
        [sys.executable, str(ROOT / "tools/mock/serve.py"), *selection, *flags],
        cwd=ROOT,
        env={**os.environ, "DATA_DIR": directory},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def ready(proc, services):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise AssertionError(proc.communicate()[0])
        try:
            for port, service in services:
                body = httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.3).json()
                assert body["ok"] and body["service"] == service, body
            return
        except (httpx.HTTPError, ValueError):
            time.sleep(0.05)
    raise AssertionError("mock servers did not become ready")


def stop(proc):
    if proc.poll() is None:
        proc.send_signal(signal.SIGINT)
    try:
        output = proc.communicate(timeout=8)[0]
    except subprocess.TimeoutExpired:
        proc.kill()
        output = proc.communicate()[0]
        raise AssertionError(f"shutdown timed out: {output}")
    assert proc.returncode == 0, output


async def streams():
    async with websockets.connect('ws://127.0.0.1:8765/ws/state') as state:
        async with websockets.connect('ws://127.0.0.1:8765/ws/coach') as coach:
            for _ in range(12):
                item = json.loads(await asyncio.wait_for(state.recv(), timeout=2))
                assert item['t'] in ('state', 'event')
            summary = json.loads(await asyncio.wait_for(coach.recv(), timeout=12))
            assert summary['t'] == 'round_summary'
            message = json.loads(await asyncio.wait_for(coach.recv(), timeout=2))
            assert message['t'] == 'coach' and message['round'] == summary['round']


async def versus_stream(sid):
    async with websockets.connect(f'ws://127.0.0.1:8765/ws/state?session={sid}') as state:
        item = json.loads(await asyncio.wait_for(state.recv(), timeout=2))
        assert item['session_id'] == sid and item['t'] in ('state', 'event'), item


def run():
    with tempfile.TemporaryDirectory() as directory:
        proc = start(directory)
        try:
            ready(proc, [(8765, 'brain'), (8766, 'replay'), (8767, 'analytics')])
            sid = httpx.get('http://127.0.0.1:8765/sessions').json()[0]['session_id']
            recording = httpx.get(f'http://127.0.0.1:8765/sessions/{sid}/recording')
            assert recording.content == SAMPLE.read_bytes()
            assert recording.headers['content-type'] == 'application/x-ndjson'
            cors = httpx.options('http://127.0.0.1:8765/config', headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'POST'})
            assert cors.headers['access-control-allow-origin'] == '*'
            asyncio.run(streams())
        finally:
            stop(proc)
        print('PASS: three real ports, recording download, CORS, both WebSockets, SIGINT shutdown')
        with socket.socket() as occupied:
            occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            occupied.bind(('127.0.0.1', 8767))
            occupied.listen()
            failed = start(directory)
            output = failed.communicate(timeout=8)[0]
            assert failed.returncode == 1 and '8767' in output, output
            proc = start(directory, '--services', 'brain,replay')
            try:
                ready(proc, [(8765, 'brain'), (8766, 'replay')])
            finally:
                stop(proc)
        print('PASS: occupied-port failure leaves no servers; brain/replay work while :8767 is occupied')
        proc = start(str(ROOT / 'data'), '--services', 'brain,replay', recording=None)
        try:
            ready(proc, [(8765, 'brain'), (8766, 'replay')])
            listed = httpx.get('http://127.0.0.1:8765/sessions', timeout=20).json()
            ids = {session['session_id'] for session in listed}
            versus_ids = {'2026-10-17T23-48-17_sahil_djin_vs_kaz', '2026-10-18T01-24-57_sahil_djin_vs_kaz'}
            assert versus_ids <= ids, listed
            assert len([session for session in listed if session['session_id'] in versus_ids and session['mode'] == 'versus']) == 2, listed
            assert [session['started_at'] for session in listed] == sorted((session['started_at'] for session in listed), reverse=True), listed
            for path in sorted((ROOT / 'data/samples').glob('*.zip')):
                with zipfile.ZipFile(path) as archive:
                    member = next(name for name in archive.namelist() if name.endswith('.jsonl') and not name.endswith('.learning.jsonl'))
                    sid = json.loads(archive.read(member.removesuffix('.jsonl') + '.session.json'))['session_id']
                    response = httpx.get(f'http://127.0.0.1:8765/sessions/{sid}/recording', timeout=10)
                    assert response.headers['content-type'] == 'application/x-ndjson', response.headers
                    assert response.content == archive.read(member), path
            asyncio.run(versus_stream('2026-10-18T01-24-57_sahil_djin_vs_kaz'))
        finally:
            stop(proc)
        print(f'PASS: automatic discovery lists {len(listed)} sessions (2 versus); exact ZIP recording downloads and neutral versus WebSocket')


if __name__ == '__main__':
    run()
