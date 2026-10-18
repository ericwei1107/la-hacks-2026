import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import sentry_sdk
from sentry_sdk.transport import Transport

transactions = []
calls = []
original_init = sentry_sdk.init


class MemoryTransport(Transport):
    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.headers.get('type') == 'transaction':
                transactions.append(item.payload.json)


def initialize(*args, **kwargs):
    calls.append(True)
    kwargs.update(dsn='https://public@example.invalid/1', transport=MemoryTransport, profile_session_sample_rate=0, enable_logs=False)
    return original_init(*args, **kwargs)


os.environ['SENTRY_ENVIRONMENT'] = 'instrumentation-test'
os.environ['SENTRY_RELEASE'] = 'kumite-analytics@instrumentation-test'
with patch('sentry_sdk.init', side_effect=initialize):
    from analytics.main import create_app

from fastapi.testclient import TestClient

with tempfile.TemporaryDirectory() as directory:
    sample = Path(directory) / 'samples'
    sample.mkdir()
    for path in (ROOT / 'data/samples').glob('practice_djin_vs_kaz*'):
        shutil.copy(path, sample / path.name)
    sid = json.loads((sample / 'practice_djin_vs_kaz.session.json').read_text())['session_id']
    with TestClient(create_app(directory)) as client:
        for endpoint in ('/health', f'/learning/{sid}', '/trends/sahil/devil_jin', f'/stats/{sid}'):
            response = client.get(endpoint)
            assert response.status_code == 200, (endpoint, response.status_code)
sentry_sdk.flush(timeout=5)
assert len(calls) == 1, calls
expected = {'/health', '/learning/{session_id}', '/trends/{player}/{character}', '/stats/{session_id}'}
assert {item['transaction'] for item in transactions} == expected, [item['transaction'] for item in transactions]
assert len(transactions) == len(expected), 'duplicate HTTP transactions'
for event in transactions:
    assert event['environment'] == 'instrumentation-test'
    assert event['release'] == 'kumite-analytics@instrumentation-test'
    assert event['contexts']['trace']['op'] == 'http.server'
operations = {span['op'] for event in transactions for span in event.get('spans', [])}
assert {'file.load', 'stats.reduce', 'learning.derive'} <= operations, operations
print(json.dumps({'transactions': sorted(expected), 'initializations': len(calls), 'network_transport': False, 'operations': sorted(operations)}))
