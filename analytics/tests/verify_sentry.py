import argparse
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


def configured_environment():
    env = dict(os.environ)
    path = ROOT / 'analytics/.env'
    if path.exists():
        for line in path.read_text().splitlines():
            parts = shlex.split(line, comments=True)
            if parts and parts[0] == 'export':
                parts = parts[1:]
            if len(parts) == 1 and '=' in parts[0]:
                name, value = parts[0].split('=', 1)
                if name in ('SENTRY_DSN', 'SENTRY_RELEASE') and not env.get(name):
                    env[name] = value
    if not env.get('SENTRY_DSN'):
        raise RuntimeError('Configure SENTRY_DSN before running live verification')
    env['SENTRY_ENVIRONMENT'] = 'verification-46'
    return env


def run():
    parser = argparse.ArgumentParser(description='Exercise real analytics startup and send verification transactions to its configured Sentry project')
    parser.add_argument('--live', action='store_true', required=True)
    parser.parse_args()
    env = configured_environment()
    with tempfile.TemporaryDirectory() as directory:
        samples = Path(directory) / 'samples'
        samples.mkdir()
        for path in (ROOT / 'data/samples').glob('practice_djin_vs_kaz*'):
            shutil.copy(path, samples / path.name)
        meta = json.loads((samples / 'practice_djin_vs_kaz.session.json').read_text())
        sid = meta['session_id']
        env['DATA_DIR'] = directory
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'analytics.main:app', '--host', '127.0.0.1', '--port', '18767', '--log-level', 'warning'], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        traces = {}
        try:
            deadline = time.monotonic() + 15
            with httpx.Client(base_url='http://127.0.0.1:18767', timeout=10) as client:
                while True:
                    if process.poll() is not None:
                        raise RuntimeError('Analytics verification server could not start')
                    try:
                        response = client.get('/health')
                        if response.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    if time.monotonic() > deadline:
                        raise RuntimeError('Analytics verification startup timed out')
                    time.sleep(0.1)
                release = env.get('SENTRY_RELEASE') or f"kumite-analytics@{response.json()['version']}"
                endpoints = {'/health': '/health', '/learning/{session_id}': f'/learning/{sid}', '/trends/{player}/{character}': '/trends/sahil/devil_jin', '/stats/{session_id}': f'/stats/{sid}'}
                for route, path in endpoints.items():
                    trace_id, parent_id = uuid.uuid4().hex, uuid.uuid4().hex[:16]
                    response = client.get(path, headers={'sentry-trace': f'{trace_id}-{parent_id}-1'})
                    if response.status_code != 200:
                        raise RuntimeError(f'Verification request failed for {route}: HTTP {response.status_code}')
                    traces[route] = trace_id
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
            try:
                process.communicate(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise RuntimeError('Verification shutdown timed out before SDK flush') from None
        if process.returncode:
            raise RuntimeError('Verification process did not shut down successfully')
        print(json.dumps({'environment': env['SENTRY_ENVIRONMENT'], 'release': release, 'traces': traces, 'shutdown': 'clean; SDK atexit flush completed'}))


if __name__ == '__main__':
    try:
        run()
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            print(str(exc), file=sys.stderr)
        else:
            print(f'Verification failed ({type(exc).__name__}); credentials omitted', file=sys.stderr)
        raise SystemExit(1)
