import argparse
import hashlib
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from analytics.insights import InsightRepository, check_id
from analytics.repository import DataError, FileRepository, ROOT, VALIDATORS, decode, validate

JSON_LIMIT = 2 * 1024 * 1024


def data_root(value):
    root = Path(value).expanduser()
    if not root.is_absolute():
        raise ValueError('Use the absolute DATA_DIR printed by the brain process')
    root = root.resolve(strict=True)
    if not root.is_dir() or not all((root / name).is_dir() for name in ('sessions', 'recordings')):
        raise ValueError('DATA_DIR must already contain sessions/ and recordings/ from the brain')
    return root


def service_url(value):
    parts = urllib.parse.urlsplit(value)
    if (parts.scheme not in ('http', 'https') or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.query or parts.fragment):
        raise ValueError('Use an HTTP service URL without credentials, query or fragment')
    parts.port
    return value.rstrip('/')


def response(base, path, timeout):
    request = urllib.request.Request(base + path, headers={'Accept': 'application/json'}, method='GET')
    return urllib.request.urlopen(request, timeout=timeout)


def remote_json(base, path, timeout):
    try:
        with response(base, path, timeout) as stream:
            content = stream.read(JSON_LIMIT + 1)
        if len(content) > JSON_LIMIT:
            raise DataError('http_json_too_large')
        return decode(content)
    except (OSError, ValueError, UnicodeError, urllib.error.URLError) as exc:
        raise DataError('http_json_unavailable_or_invalid') from exc


def remote_digest(base, path, length, timeout):
    value = hashlib.sha256()
    try:
        with response(base, path, timeout) as stream:
            remaining = length
            while remaining:
                chunk = stream.read(min(65536, remaining))
                if not chunk:
                    raise DataError('brain_recording_shorter_than_local_prefix')
                remaining -= len(chunk)
                value.update(chunk)
        return value.hexdigest()
    except (OSError, urllib.error.URLError) as exc:
        raise DataError('brain_recording_unavailable') from exc


def inspect_once(root, sid, brain_url, analytics_url, timeout):
    meta = decode((root / 'sessions' / f'{sid}.json').read_bytes())
    validate(meta, VALIDATORS['session'], 'local metadata')
    recording = root / 'recordings' / f'{sid}.jsonl'
    reference = Path(meta.get('recording') or recording)
    reference = reference if reference.is_absolute() else ROOT / reference
    if reference.resolve() != recording.resolve():
        raise DataError('metadata_recording_points_outside_the_selected_canonical_folder')
    insights = InsightRepository(root)
    before = insights.snapshot(sid, limit=1)
    if before is None:
        raise DataError('local_session_missing')
    repository = FileRepository(root)
    expected_stats = repository.stats(sid)
    expected_learning = repository.learning(sid)
    checks = {}
    versions = {}
    for name, url in (('brain', brain_url), ('analytics', analytics_url)):
        health = remote_json(url, '/health', timeout)
        checks[name + '_health_identity'] = (isinstance(health, dict) and health.get('ok') is True
                                            and health.get('service') == name and isinstance(health.get('version'), str))
        versions[name] = health.get('version') if isinstance(health, dict) else None
    remote_meta = remote_json(brain_url, '/sessions/' + urllib.parse.quote(sid, safe=''), timeout)
    validate(remote_meta, VALIDATORS['session'], 'brain metadata')
    identity = ('session_id', 'started_at', 'player', 'human_slot', 'human_character', 'bot_character', 'difficulty', 'mode')
    checks['brain_session_identity'] = all(remote_meta.get(key) == meta.get(key) for key in identity)
    source = before['sources']['recording']
    brain_hash = remote_digest(brain_url, '/sessions/' + urllib.parse.quote(sid, safe='') + '/recording', source['consumed_bytes'], timeout)
    checks['brain_recording_prefix'] = brain_hash == source['sha256']
    actual_stats = remote_json(analytics_url, '/stats/' + urllib.parse.quote(sid, safe=''), timeout)
    actual_learning = remote_json(analytics_url, '/learning/' + urllib.parse.quote(sid, safe=''), timeout)
    checks['analytics_stats_match_local'] = actual_stats == expected_stats
    checks['analytics_learning_match_local'] = actual_learning == expected_learning
    after = insights.snapshot(sid, limit=1)
    if after is None or before['snapshot_id'] != after['snapshot_id']:
        raise DataError('source_changed_during_check')
    checks['source_quality'] = (before['quality']['state'] != 'invalid'
                                and not any(m['state'] == 'invalid' for m in before['metrics'].values()))
    freshness = before['freshness']
    learning_ready = (bool(freshness['completed_rounds']) and not freshness['pending_learning_rounds']
                      and not freshness['learning_ahead_rounds'] and not before['sources']['learning']['pending_tail'])
    exit_code = 1 if not all(checks.values()) else 0 if learning_ready else 2
    return {'session_id': sid, 'data_dir': str(root), 'mode': 'source_snapshot', 'checks': checks,
            'versions': versions, 'snapshot_id': before['snapshot_id'], 'freshness': freshness,
            'recording_prefix': {'bytes': source['consumed_bytes'], 'pending_tail': source['pending_tail'],
                                 'local_sha256': source['sha256'], 'brain_sha256': brain_hash},
            'learning_ready': learning_ready, 'exit_code': exit_code}


def inspect(root, sid, brain_url, analytics_url, timeout=2):
    check_id(sid)
    root = data_root(root)
    brain_url, analytics_url = service_url(brain_url), service_url(analytics_url)
    for attempt in range(2):
        try:
            return inspect_once(root, sid, brain_url, analytics_url, timeout)
        except (DataError, OSError, ValueError, UnicodeError):
            if attempt:
                return {'session_id': sid, 'data_dir': str(root), 'mode': 'source_snapshot',
                        'exit_code': 1, 'error': 'Source or HTTP data is unavailable, invalid or changing; check the configured folder and services, then retry'}


def serve(root, host, port, file_only=False):
    root = data_root(root)
    os.environ['DATA_DIR'] = str(root)
    if file_only:
        os.environ['DATABASE_URL'] = ''
    print(f'Analytics DATA_DIR={root}', flush=True)
    print(f'Listening on {host}:{port}; no .env file is loaded by this launcher', flush=True)
    import uvicorn
    uvicorn.run('analytics.main:app', host=host, port=port)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run analytics beside the brain or verify the shared source through existing read-only APIs')
    actions = parser.add_subparsers(dest='action', required=True)
    launch = actions.add_parser('serve')
    launch.add_argument('--data-dir', required=True)
    launch.add_argument('--host', default='127.0.0.1')
    launch.add_argument('--port', type=int, default=8767)
    launch.add_argument('--file-only', action='store_true')
    check = actions.add_parser('check')
    check.add_argument('--data-dir', required=True)
    check.add_argument('--session-id', required=True)
    check.add_argument('--brain-url', default=os.environ.get('KUMITE_BRAIN_URL') or 'http://127.0.0.1:8765')
    check.add_argument('--analytics-url', default=os.environ.get('KUMITE_ANALYTICS_URL') or 'http://127.0.0.1:8767')
    check.add_argument('--timeout-seconds', type=float, default=2)
    args = parser.parse_args(argv)
    try:
        if args.action == 'serve':
            if not 1 <= args.port <= 65535:
                raise ValueError('Port must be between 1 and 65535')
            serve(args.data_dir, args.host, args.port, args.file_only)
            return 0
        if not math.isfinite(args.timeout_seconds) or not 0 < args.timeout_seconds <= 30:
            raise ValueError('Timeout must be finite, positive and at most 30 seconds')
        report = inspect(args.data_dir, args.session_id, args.brain_url, args.analytics_url, args.timeout_seconds)
    except (OSError, ValueError):
        parser.exit(1, 'Invalid host configuration: use an existing absolute brain DATA_DIR, safe session id and credential-free service URLs\n')
    print(json.dumps(report, indent=2, allow_nan=False))
    return report['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
