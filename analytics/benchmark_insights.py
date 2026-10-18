import argparse
import hashlib
import json
import math
import platform
import statistics
import subprocess
import time

from analytics.insights import InsightRepository
from analytics.repository import DataError, ROOT


def measure(repository, sid, repetitions=20):
    snapshot = repository.snapshot(sid)
    if snapshot is None:
        raise ValueError('Unknown session')
    values = []
    for _ in range(repetitions):
        before = time.perf_counter()
        current = repository.snapshot(sid)
        values.append((time.perf_counter() - before) * 1000)
        if current is None or current['snapshot_id'] != snapshot['snapshot_id']:
            raise DataError('Benchmark source changed; repeat with a static fixture')
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, stderr=subprocess.DEVNULL, timeout=2).strip()
    except (OSError, subprocess.SubprocessError):
        commit = 'unknown'
    code = {f'analytics/{name}': hashlib.sha256((ROOT / 'analytics' / name).read_bytes()).hexdigest()
            for name in ('stats.py', 'evidence.py', 'focus.py', 'insights.py', 'insights.schema.json', 'benchmark_insights.py')}
    return {'measurement': 'cached internal capture/hash and snapshot; not HTTP or game-loop timing',
            'session_id': sid, 'snapshot_id': snapshot['snapshot_id'], 'base_commit': commit, 'code_sha256': code,
            'platform': platform.platform(), 'python': platform.python_version(), 'samples': repetitions,
            'p50_ms': round(statistics.median(values), 3),
            'p95_ms': round(sorted(values)[math.ceil(.95 * len(values)) - 1], 3),
            'max_ms': round(max(values), 3), 'engineering_target_ms': 250,
            'native_host_acceptance': 'not_established'}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Measure cached internal insight derivation without cloud/provider requests')
    parser.add_argument('session_id')
    parser.add_argument('--data-dir', default='./data')
    parser.add_argument('--repetitions', type=int, default=20)
    args = parser.parse_args(argv)
    if not 10 <= args.repetitions <= 1000:
        parser.error('repetitions must be between 10 and 1000')
    try:
        result = measure(InsightRepository(args.data_dir), args.session_id, args.repetitions)
    except (DataError, ValueError, OSError):
        parser.exit(1, 'Cannot benchmark this session: missing, invalid or changing source\n')
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
