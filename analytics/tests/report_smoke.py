import json
import hashlib
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from analytics.repository import VALIDATORS


def free_port():
    with socket.socket() as bound:
        bound.bind(('127.0.0.1', 0))
        return bound.getsockname()[1]


def run_bundle(bundle, temp):
    data = temp / bundle
    original = ROOT / 'data/samples' / bundle
    identity = {str(path.relative_to(original)): hashlib.sha256(path.read_bytes()).hexdigest() for path in original.rglob('*') if path.is_file()}
    shutil.copytree(original, data)
    meta = json.loads(next((data / 'sessions').glob('*.json')).read_text())
    sid = meta['session_id']
    lines = (data / 'recordings' / f'{sid}.jsonl').read_text().splitlines()
    port = free_port()
    environment = {**os.environ, 'DATA_DIR': str(data), 'SENTRY_DSN': '', 'DATABASE_URL': '',
                   'KUMITE_COACH_MODE': 'local', 'KUMITE_JEV_MODE': 'local',
                   'OPENAI_API_KEY': '', 'JEV_API_KEY': '', 'TYPESAFE_API_KEY': ''}
    with tempfile.TemporaryFile(mode='w+t') as log:
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'replay.main:app', '--host', '127.0.0.1', '--port', str(port), '--log-level', 'warning'],
                                   cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=60, trust_env=False) as client:
                deadline = time.monotonic() + 20
                while True:
                    if process.poll() is not None:
                        log.seek(0)
                        raise AssertionError('Replay failed to start; install its dependencies in the verification environment: ' + log.read()[-1500:])
                    try:
                        response = client.get('/health', timeout=1)
                        response.raise_for_status()
                        assert response.json()['service'] == 'replay'
                        break
                    except (httpx.HTTPError, ValueError):
                        if time.monotonic() >= deadline:
                            raise AssertionError('Replay health timed out')
                        time.sleep(.1)
                response = client.post(f'/analyze/{sid}')
                response.raise_for_status()
                report = response.json()
                VALIDATORS['report'].validate(report)
                assert report['session_id'] == sid
                assert report['synthetic'] == (bundle == 'synthetic')
                assert report['scoring_summary']['scored'] == 0
                saved = client.get(f'/reports/{sid}')
                saved.raise_for_status()
                assert saved.json() == report
                checked = 0
                for point in report['decision_points']:
                    assert point['scoring']['status'] == 'unavailable'
                    assert point['best'] == 'unavailable'
                    assert point['options'] == []
                    for evidence in point['evidence']:
                        source = json.loads(lines[evidence['line'] - 1])
                        assert source['round'] == point['round']
                        assert source['frame'] == point['frame']
                        checked += 1
                for habit in report['habits']:
                    for evidence in habit['evidence']:
                        source = json.loads(lines[evidence['line'] - 1])
                        assert (source['round'], source['frame']) == (evidence['round'], evidence['frame'])
                        checked += 1
                assert identity == {str(path.relative_to(original)): hashlib.sha256(path.read_bytes()).hexdigest() for path in original.rglob('*') if path.is_file()}
                print(f'PASS: real replay HTTP analyze/saved GET, {bundle}, {len(report["decision_points"])} decisions, {checked} source citations, honest unscored labels')
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                raise AssertionError('Replay shutdown timed out')
            assert process.returncode == 0, 'Replay exited abnormally'


def run():
    with tempfile.TemporaryDirectory() as temporary:
        for bundle in ('synthetic', 'live_learning'):
            run_bundle(bundle, Path(temporary))
    print('PASS: replay processes stopped; original fixtures unchanged; provider, database and telemetry disabled')


if __name__ == '__main__':
    run()
