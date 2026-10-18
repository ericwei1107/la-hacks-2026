import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from analytics.demo_host import inspect
from analytics.insight_examples import REAL_ID


def free_port():
    with socket.socket() as stream:
        stream.bind(('127.0.0.1', 0))
        return stream.getsockname()[1]


def fingerprints(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def run():
    fixture = ROOT / 'data/samples/live_learning'
    original = fingerprints(fixture)
    processes = []
    with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryFile(mode='w+t') as log:
        root = Path(temporary) / 'live'
        shutil.copytree(fixture, root)
        meta_path = root / 'sessions' / f'{REAL_ID}.json'
        metadata = json.loads(meta_path.read_text())
        recording = root / 'recordings' / f'{REAL_ID}.jsonl'
        metadata['recording'] = f'data/recordings/{REAL_ID}.jsonl'
        assert not (ROOT / metadata['recording']).exists()
        meta_path.write_text(json.dumps(metadata), encoding='utf-8')
        brain_port, analytics_port = free_port(), free_port()
        brain_url, analytics_url = f'http://127.0.0.1:{brain_port}', f'http://127.0.0.1:{analytics_port}'
        environment = {**os.environ, 'DATA_DIR': str(root), 'SENTRY_DSN': '', 'DATABASE_URL': '',
                       'OPENAI_API_KEY': '', 'JEV_API_KEY': '', 'TYPESAFE_API_KEY': ''}
        try:
            commands = [
                ['-m', 'game.api', '--host', '127.0.0.1', '--port', str(brain_port)],
                ['-m', 'analytics.demo_host', 'serve', '--data-dir', str(root), '--port', str(analytics_port), '--file-only'],
            ]
            for command in commands:
                processes.append(subprocess.Popen([sys.executable, *command], cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT))
            with httpx.Client(timeout=1, trust_env=False) as client:
                deadline = time.monotonic() + 20
                while True:
                    if any(p.poll() is not None for p in processes):
                        raise AssertionError('A temporary verification service stopped before becoming healthy')
                    try:
                        for url, name in ((brain_url, 'brain'), (analytics_url, 'analytics')):
                            response = client.get(url + '/health')
                            response.raise_for_status()
                            assert response.json()['service'] == name
                        break
                    except (httpx.HTTPError, ValueError):
                        if time.monotonic() >= deadline:
                            raise AssertionError('Temporary host-check service health timed out')
                        time.sleep(.1)
            check = subprocess.run([sys.executable, '-m', 'analytics.demo_host', 'check', '--data-dir', str(root),
                                    '--session-id', REAL_ID, '--brain-url', brain_url, '--analytics-url', analytics_url],
                                   cwd=ROOT, env=environment, capture_output=True, text=True, timeout=60)
            assert check.returncode == 0, check.stderr
            value = json.loads(check.stdout)
            assert value['exit_code'] == 0, value
            assert all(value['checks'].values()), value
            assert value['freshness']['completed_rounds'] == [1, 2, 3, 4]
            new_event = {'t': 'event', 'session_id': REAL_ID, 'round': 5, 'frame': 10, 'kind': 'hit',
                         'actor': 1, 'target': 0, 'hit_level': 'low', 'damage': 10}
            content = json.dumps(new_event).encode('utf-8')
            with recording.open('ab') as stream:
                stream.write(content[:20])
            partial = inspect(root, REAL_ID, brain_url, analytics_url)
            assert partial['exit_code'] == 0 and partial['recording_prefix']['pending_tail'], partial
            assert partial['freshness']['latest_recording_round'] == 4
            with recording.open('ab') as stream:
                stream.write(content[20:] + b'\n')
                stream.write(json.dumps({'t': 'event', 'session_id': REAL_ID, 'round': 5, 'frame': 100, 'kind': 'round_end', 'detail': {'winner': 1}}).encode() + b'\n')
            pending = inspect(root, REAL_ID, brain_url, analytics_url)
            assert pending['exit_code'] == 2, pending
            assert pending['freshness']['pending_learning_rounds'] == [5]
            with (root / 'learning' / f'{REAL_ID}.jsonl').open('a', encoding='utf-8', newline='\n') as stream:
                stream.write(json.dumps({'t': 'learning_round', 'session_id': REAL_ID, 'round': 5, 'prediction_accuracy': None, 'habits': {}}) + '\n')
            current = inspect(root, REAL_ID, brain_url, analytics_url)
            assert current['exit_code'] == 0, current
            assert current['freshness']['pending_learning_rounds'] == []
            assert current['snapshot_id'] != pending['snapshot_id']
            watcher = subprocess.Popen([sys.executable, '-m', 'analytics.demo_host', 'check', '--data-dir', str(root),
                                        '--session-id', 'latest', '--wait-for-round-seconds', '60',
                                        '--brain-url', brain_url, '--analytics-url', analytics_url],
                                       cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            time.sleep(8)
            with recording.open('ab') as stream:
                stream.write(json.dumps({**new_event, 'round': 6}).encode() + b'\n')
                stream.write(json.dumps({'t': 'event', 'session_id': REAL_ID, 'round': 6, 'frame': 100, 'kind': 'round_end', 'detail': {'winner': 1}}).encode() + b'\n')
            time.sleep(3)
            with (root / 'learning' / f'{REAL_ID}.jsonl').open('a', encoding='utf-8', newline='\n') as stream:
                stream.write(json.dumps({'t': 'learning_round', 'session_id': REAL_ID, 'round': 6, 'prediction_accuracy': None, 'habits': {}}) + '\n')
            out, err = watcher.communicate(timeout=90)
            observed = json.loads(out)
            assert watcher.returncode == 0 and observed['exit_code'] == 0 and observed['advanced'], (observed, err)
            assert observed['session_id'] == REAL_ID
            assert observed['before']['freshness']['completed_rounds'][-1] == 5, observed['before']
            assert observed['after']['freshness']['completed_rounds'][-1] == 6, observed['after']
            assert all(observed['after']['checks'].values()), observed['after']
            stop = threading.Event()
            def live_round():
                frame = 0
                while not stop.is_set():
                    frame += 1
                    with recording.open('ab') as stream:
                        stream.write(json.dumps({**new_event, 'round': 7, 'frame': frame}).encode() + b'\n')
                    time.sleep(.02)
            writer = threading.Thread(target=live_round)
            writer.start()
            try:
                time.sleep(.5)
                live = inspect(root, REAL_ID, brain_url, analytics_url)
            finally:
                stop.set()
                writer.join()
            assert live['exit_code'] == 0 and live['comparison'] == 'completed_rounds_while_appending', live
            assert all(live['checks'].values()) and live['freshness']['latest_recording_round'] == 7, live
            wrong = Path(temporary) / 'wrong'
            shutil.copytree(root, wrong)
            meta = json.loads((wrong / 'sessions' / f'{REAL_ID}.json').read_text())
            meta['recording'] = str(wrong / 'recordings' / f'{REAL_ID}.jsonl')
            (wrong / 'sessions' / f'{REAL_ID}.json').write_text(json.dumps(meta), encoding='utf-8')
            wrong_recording = wrong / 'recordings' / f'{REAL_ID}.jsonl'
            before = wrong_recording.read_bytes()
            changed = before.replace(content, content.replace(b'"damage": 10', b'"damage": 11'), 1)
            assert changed != before and len(changed) == len(before)
            wrong_recording.write_bytes(changed)
            mismatch = inspect(wrong, REAL_ID, brain_url, analytics_url)
            assert mismatch['exit_code'] == 1, mismatch
            assert not mismatch.get('checks', {}).get('brain_recording_prefix', True), mismatch
            print('PASS: actual brain/analytics HTTP routes share a temporary canonical source; recorder-relative metadata, complete-prefix reads, delayed learning, one-command before/after round capture, checks during continuous writes and wrong-folder detection verified')
        finally:
            for process in processes:
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
            for process in processes:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                    raise AssertionError('Temporary verification service did not stop cleanly')
                assert process.returncode == 0, process.returncode
            assert fingerprints(fixture) == original, 'The checked-in real fixture changed'
    print('PASS: temporary services stopped; original fixture preserved; no game, provider, cloud or telemetry activity')


if __name__ == '__main__':
    run()
