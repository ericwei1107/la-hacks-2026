import asyncio
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[2]
SID = '2026-10-17T13-05-00_synth_djin_vs_kaz'


def start(args, directory):
    return subprocess.Popen([sys.executable, *args],cwd=ROOT,env={**os.environ,'DATA_DIR':str(directory),'SENTRY_DSN':''},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)


def ready(processes):
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        for process in processes:
            if process.poll() is not None:
                raise AssertionError(process.communicate()[0])
        try:
            for port,name in [(8765,'brain'),(8766,'replay'),(8767,'analytics')]:
                body=httpx.get(f'http://127.0.0.1:{port}/health',timeout=1).json()
                assert body['ok'] and body['service']==name,body
            return
        except (httpx.HTTPError, ValueError):
            time.sleep(0.05)
    raise AssertionError('Services did not become ready')


async def stream():
    async with websockets.connect('ws://127.0.0.1:8765/ws/state') as websocket:
        record=json.loads(await asyncio.wait_for(websocket.recv(),3))
        assert record['session_id']==SID


def run():
    with tempfile.TemporaryDirectory() as directory:
        directory=Path(directory)
        subprocess.run([sys.executable,'tools/mock/synth.py','--out',str(directory)],cwd=ROOT,check=True,capture_output=True,text=True)
        processes=[]
        try:
            processes.append(start(['tools/mock/serve.py','--services','brain,replay','--recording',str(directory/'recordings'/f'{SID}.jsonl'),'--rate','600'],directory))
            processes.append(start(['-m','uvicorn','analytics.main:app','--host','127.0.0.1','--port','8767','--log-level','warning'],directory))
            ready(processes)
            base='http://127.0.0.1:8767'
            metrics=httpx.get(f'{base}/learning/{SID}').json()
            assert metrics['time_to_detect']['low_defense']==1,metrics
            assert metrics['time_to_mastery']['low_defense']==3,metrics
            assert [r['prediction_accuracy'] for r in metrics['rounds']]==[0.41,0.58,0.71]
            values=httpx.get(f'{base}/trends/synth/devil_jin',timeout=10).json()['series'][0]['values']
            assert values['mastery:low_defense']==0.88,values
            assert values['win_rate:difficulty:3']==0.333,values
            assert httpx.get(f'{base}/learning/not-a-session').status_code==404
            (directory/'eval').mkdir()
            (directory/'eval'/f'{SID}.json').write_text(json.dumps({'before':0.4,'after':0.8}))
            assert httpx.get(f'{base}/learning/{SID}').json()['finetune']=={'before':0.4,'after':0.8}
            asyncio.run(stream())
            print('PASS: real analytics + mock brain/replay; learning, trends, live evaluation refresh and WebSocket playback')
        finally:
            for process in processes:
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
            for process in processes:
                try:
                    output=process.communicate(timeout=8)[0]
                except subprocess.TimeoutExpired:
                    process.kill()
                    output=process.communicate()[0]
                    raise AssertionError(f'Shutdown timed out: {output}')
                assert process.returncode==0,output
        print('PASS: all test services shut down cleanly')


if __name__=='__main__':
    run()
