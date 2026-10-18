import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SERVICES = ('brain', 'replay', 'analytics')
VARIABLES = {'brain': 'KUMITE_BRAIN_URL', 'replay': 'KUMITE_REPLAY_URL', 'analytics': 'KUMITE_ANALYTICS_URL'}
DEFAULTS = {'brain': 'http://localhost:8765', 'replay': 'http://localhost:8766', 'analytics': 'http://localhost:8767'}
DETAIL_LIMIT = 160
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NO_ADVANCE = 2


def resolve_urls(env):
    return {name: (env.get(VARIABLES[name], '').strip() or DEFAULTS[name]).rstrip('/') for name in SERVICES}


def display_url(url):
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ''
    if parts.port:
        host = f'{host}:{parts.port}'
    return urllib.parse.urlunsplit((parts.scheme, host, parts.path, '', ''))


def bounded(text):
    text = ' '.join(str(text).split())
    return text if len(text) <= DETAIL_LIMIT else text[:DETAIL_LIMIT - 1] + '…'


def fetch(url, timeout):
    request = urllib.request.Request(url, headers={'Accept': 'application/json'}, method='GET')
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        try:
            body = error.read()
        except OSError:
            body = b''
        return {'kind': 'status', 'status': error.code, 'detail': bounded(body.decode('utf-8', 'replace'))}
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as error:
        reason = getattr(error, 'reason', error)
        return {'kind': 'unreachable', 'detail': bounded(f'{type(reason).__name__}: {reason}')}
    try:
        value = json.loads(body)
    except ValueError:
        return {'kind': 'malformed', 'status': status, 'detail': 'response is not JSON'}
    return {'kind': 'json', 'status': status, 'value': value}


def check_health(name, base, timeout):
    result = {'url': display_url(base)}
    response = fetch(f'{base}/health', timeout)
    if response['kind'] == 'unreachable':
        return {**result, 'status': 'unreachable', 'detail': response['detail']}
    if response['kind'] == 'status':
        return {**result, 'status': 'failed', 'detail': f"HTTP {response['status']}: {response['detail']}"}
    if response['kind'] == 'malformed':
        return {**result, 'status': 'malformed', 'detail': response['detail']}
    value = response['value']
    if not isinstance(value, dict) or value.get('ok') is not True:
        return {**result, 'status': 'malformed', 'detail': 'health reply does not say ok: true'}
    if value.get('service') != name:
        return {**result, 'status': 'malformed', 'detail': bounded(f"health reply names service {value.get('service')!r}, expected {name!r}")}
    version = value.get('version')
    return {**result, 'status': 'ok', 'version': version if isinstance(version, str) else None}


def completed_rounds(value, session_id):
    if not isinstance(value, dict):
        return None, 'reply is not a JSON object'
    if value.get('session_id') != session_id:
        return None, bounded(f"reply is for session {value.get('session_id')!r}")
    rounds = value.get('rounds')
    if not isinstance(rounds, list):
        return None, 'reply has no rounds list'
    numbers = []
    for entry in rounds:
        number = entry.get('round') if isinstance(entry, dict) else None
        if not isinstance(number, int) or isinstance(number, bool):
            return None, 'a round entry has no integer round'
        numbers.append(number)
    return sorted(set(numbers)), None


def read_rounds(kind, base, session_id, timeout):
    response = fetch(f'{base}/{kind}/{urllib.parse.quote(session_id, safe="")}', timeout)
    if response['kind'] == 'unreachable':
        return {'status': 'unreachable', 'detail': response['detail']}
    if response['kind'] == 'status':
        code = response['status']
        status = 'missing_session' if code == 404 else 'unavailable' if code == 503 else 'failed'
        return {'status': status, 'detail': f"HTTP {code}: {response['detail']}"}
    if response['kind'] == 'malformed':
        return {'status': 'malformed', 'detail': response['detail']}
    rounds, problem = completed_rounds(response['value'], session_id)
    if problem:
        return {'status': 'malformed', 'detail': problem}
    if kind == 'stats' and not isinstance(response['value'].get('totals'), dict):
        return {'status': 'malformed', 'detail': 'stats reply has no totals object'}
    if kind == 'learning' and not rounds:
        return {'status': 'incomplete', 'rounds': [], 'detail': 'no completed learning rounds yet; this is missing data, not a measured zero'}
    return {'status': 'ok', 'rounds': rounds}


def latest(reading):
    rounds = reading.get('rounds') or []
    return rounds[-1] if rounds else None


def advanced_past(reading, baseline):
    if reading.get('status') != 'ok':
        return None
    later = [number for number in reading['rounds'] if baseline is None or number > baseline]
    return later[-1] if later else None


def run(session_id, urls, watch_seconds=0.0, poll_seconds=5.0, timeout_seconds=5.0, require_advance=False, clock=time.monotonic, sleep=time.sleep):
    services = {name: check_health(name, urls[name], timeout_seconds) for name in SERVICES}
    analytics = urls['analytics']
    stats = read_rounds('stats', analytics, session_id, timeout_seconds)
    learning = read_rounds('learning', analytics, session_id, timeout_seconds)
    baseline = {'stats': latest(stats), 'learning': latest(learning)}
    reached = {'stats': None, 'learning': None}
    resets = []
    polls = 0
    deadline = clock() + max(0.0, watch_seconds)
    while services['analytics']['status'] == 'ok' and clock() < deadline:
        if require_advance and reached['stats'] is not None and reached['learning'] is not None:
            break
        sleep(min(poll_seconds, max(0.0, deadline - clock())))
        remaining = deadline - clock()
        if remaining <= 0:
            break
        request_timeout = min(timeout_seconds, max(0.1, remaining))
        polls += 1
        for kind in ('stats', 'learning'):
            reading = read_rounds(kind, analytics, session_id, request_timeout)
            previous = latest(stats if kind == 'stats' else learning)
            current = latest(reading)
            if reading['status'] == 'ok' and previous is not None and current is not None and current < previous:
                resets.append(f'{kind} went back from round {previous} to {current}')
            if kind == 'stats':
                stats = reading
            else:
                learning = reading
            reached[kind] = advanced_past(reading, baseline[kind])
    advanced = reached['stats'] is not None and reached['learning'] is not None
    report = {
        'session_id': session_id,
        'mode': 'watch' if watch_seconds > 0 else 'snapshot',
        'watch_seconds': watch_seconds,
        'polls': polls,
        'services': services,
        'stats': stats,
        'learning': learning,
        'advance': {
            'required': require_advance,
            'initial': baseline,
            'reached': reached,
            'advanced': advanced,
            'resets': resets
        }
    }
    report['exit_code'] = outcome(report)
    return report


def outcome(report):
    usable = all(service['status'] == 'ok' for service in report['services'].values())
    usable = usable and report['stats']['status'] == 'ok' and report['learning']['status'] == 'ok'
    if not usable:
        return EXIT_FAILED
    if report['advance']['required'] and not report['advance']['advanced']:
        return EXIT_NO_ADVANCE
    return EXIT_OK


def rounds_text(reading):
    rounds = reading.get('rounds')
    if reading['status'] != 'ok':
        return reading.get('detail', '')
    return f"{len(rounds)} completed round{'s' if len(rounds) != 1 else ''}, latest {rounds[-1] if rounds else 'none'}"


def summary(report):
    lines = [f"Kumite integration check, session {report['session_id']} ({report['mode']})"]
    for name, service in report['services'].items():
        extra = f" version {service['version']}" if service.get('version') else ''
        detail = f" {service['detail']}" if service.get('detail') else ''
        lines.append(f"  {name:<10} {service['status']:<16} {service['url']}{extra}{detail}")
    lines.append(f"  {'stats':<10} {report['stats']['status']:<16} {rounds_text(report['stats'])}")
    lines.append(f"  {'learning':<10} {report['learning']['status']:<16} {rounds_text(report['learning'])}")
    advance = report['advance']
    if report['mode'] == 'snapshot':
        lines.append(f"  {'advance':<10} {'not watched':<16} a snapshot does not prove live writes")
    else:
        reached = advance['reached']
        state = 'advanced' if advance['advanced'] else 'no advance'
        lines.append(f"  {'advance':<10} {state:<16} stats latest {advance['initial']['stats']} then {reached['stats'] or 'no new round'}, learning latest {advance['initial']['learning']} then {reached['learning'] or 'no new round'}, over {report['polls']} polls")
    for reset in advance['resets']:
        lines.append(f"  {'reset':<10} {'not counted':<16} {reset}")
    verdict = {EXIT_OK: 'requirements met', EXIT_FAILED: 'failed or unusable responses', EXIT_NO_ADVANCE: 'healthy, but no new completed round in both stats and learning in time'}
    lines.append(f"Result: {verdict[report['exit_code']]} (exit {report['exit_code']})")
    return '\n'.join(lines)


def parse(argv):
    parser = argparse.ArgumentParser(prog='python -m analytics.integration_check', description='Read-only readiness check of the brain, replay and analytics services for one session.')
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--watch-seconds', type=float, default=0.0, help='keep polling stats and learning for this long (default 0: one snapshot)')
    parser.add_argument('--poll-seconds', type=float, default=5.0, help='wait between polls while watching (default 5)')
    parser.add_argument('--timeout-seconds', type=float, default=5.0, help='limit for each request (default 5)')
    parser.add_argument('--require-advance', action='store_true', help='require a later completed round in both stats and learning while watching')
    parser.add_argument('--json', action='store_true', help='print the report as JSON')
    args = parser.parse_args(argv)
    if args.watch_seconds < 0 or args.poll_seconds <= 0 or args.timeout_seconds <= 0:
        parser.error('--watch-seconds must be 0 or more; --poll-seconds and --timeout-seconds must be positive')
    if args.require_advance and args.watch_seconds <= 0:
        parser.error('--require-advance needs --watch-seconds')
    return args


def main(argv=None, env=None, out=None):
    args = parse(argv)
    report = run(
        args.session_id,
        resolve_urls(os.environ if env is None else env),
        watch_seconds=args.watch_seconds,
        poll_seconds=args.poll_seconds,
        timeout_seconds=args.timeout_seconds,
        require_advance=args.require_advance
    )
    stream = out or sys.stdout
    stream.write((json.dumps(report, indent=2) if args.json else summary(report)) + '\n')
    return report['exit_code']


if __name__ == '__main__':
    sys.exit(main())
