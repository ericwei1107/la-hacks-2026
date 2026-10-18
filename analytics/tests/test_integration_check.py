import io
import json
import socket
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from analytics import integration_check as check

SID = '2026-10-18T05-14-03_sahil_djin_vs_kaz'


def stats(rounds, sid=SID):
    return {'session_id': sid, 'rounds': [{'round': number, 'low_block_rate': None} for number in rounds], 'totals': {'low_block_rate': None}}


def learning(rounds, sid=SID):
    return {'session_id': sid, 'rounds': [{'round': number, 'prediction_accuracy': 0.6, 'habits': {}} for number in rounds]}


def health(name):
    return {'ok': True, 'service': name, 'version': 'test'}


class Stub:
    def __init__(self, routes):
        self.routes = routes
        self.counts = {}
        self.methods = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                stub.methods.append('GET')
                stub.reply(self)

            def do_POST(self):
                stub.methods.append('POST')
                self.send_response(405)
                self.end_headers()

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f'http://127.0.0.1:{self.server.server_address[1]}'

    def reply(self, handler):
        route = self.routes.get(handler.path)
        if route is None:
            handler.send_response(404)
            handler.end_headers()
            handler.wfile.write(b'{"detail": "Not Found"}')
            return
        if isinstance(route, list):
            index = self.counts.get(handler.path, 0)
            self.counts[handler.path] = index + 1
            route = route[min(index, len(route) - 1)]
        status, body, delay = (route + (0,))[:3] if isinstance(route, tuple) else (200, route, 0)
        if delay:
            time.sleep(delay)
        payload = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        try:
            handler.send_response(status)
            handler.send_header('Content-Type', 'application/json')
            handler.end_headers()
            handler.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def closed_port_url():
    probe = socket.socket()
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    probe.close()
    return f'http://127.0.0.1:{port}'


class IntegrationCheckTest(unittest.TestCase):
    def services(self, analytics_routes, prefix=''):
        brain = Stub({'/health': health('brain')})
        replay = Stub({'/health': health('replay')})
        routes = {'/health': health('analytics')}
        routes.update(analytics_routes)
        analytics = Stub({prefix + path: value for path, value in routes.items()})
        for stub in (brain, replay, analytics):
            self.addCleanup(stub.close)
        self.stubs = (brain, replay, analytics)
        return {'brain': brain.url, 'replay': replay.url, 'analytics': analytics.url + prefix}

    def healthy(self, stats_route=None, learning_route=None):
        return self.services({
            f'/stats/{SID}': stats_route if stats_route is not None else stats([1, 2, 3, 4]),
            f'/learning/{SID}': learning_route if learning_route is not None else learning([1, 2, 3, 4])
        })

    def run_check(self, urls, **options):
        options.setdefault('timeout_seconds', 2.0)
        return check.run(SID, urls, **options)

    def test_all_healthy_snapshot(self):
        report = self.run_check(self.healthy())
        self.assertEqual(report['exit_code'], check.EXIT_OK)
        self.assertEqual({name: service['status'] for name, service in report['services'].items()}, {'brain': 'ok', 'replay': 'ok', 'analytics': 'ok'})
        self.assertEqual(report['stats']['rounds'], [1, 2, 3, 4])
        self.assertEqual(report['learning']['rounds'], [1, 2, 3, 4])
        self.assertEqual(report['mode'], 'snapshot')
        self.assertIn('a snapshot does not prove live writes', check.summary(report))
        for stub in self.stubs:
            self.assertEqual(set(stub.methods), {'GET'})

    def test_one_service_unavailable(self):
        urls = self.healthy()
        urls['replay'] = closed_port_url()
        report = self.run_check(urls)
        self.assertEqual(report['services']['replay']['status'], 'unreachable')
        self.assertEqual(report['services']['brain']['status'], 'ok')
        self.assertEqual(report['exit_code'], check.EXIT_FAILED)

    def test_malformed_responses(self):
        urls = self.healthy(stats_route=(200, 'not json'), learning_route=learning([1, 2], sid='another-session'))
        report = self.run_check(urls)
        self.assertEqual(report['stats']['status'], 'malformed')
        self.assertEqual(report['learning']['status'], 'malformed')
        self.assertIn('another-session', report['learning']['detail'])
        self.assertEqual(report['exit_code'], check.EXIT_FAILED)

    def test_health_identity_must_match(self):
        brain = Stub({'/health': health('replay')})
        self.addCleanup(brain.close)
        urls = self.healthy()
        urls['brain'] = brain.url
        report = self.run_check(urls)
        self.assertEqual(report['services']['brain']['status'], 'malformed')
        self.assertEqual(report['exit_code'], check.EXIT_FAILED)

    def test_missing_session_and_unavailable_data(self):
        urls = self.healthy(stats_route=(404, {'detail': 'Unknown session'}), learning_route=(503, {'detail': 'learning file unreadable'}))
        report = self.run_check(urls)
        self.assertEqual(report['stats']['status'], 'missing_session')
        self.assertEqual(report['learning']['status'], 'unavailable')
        self.assertIn('HTTP 503', report['learning']['detail'])
        self.assertEqual(report['exit_code'], check.EXIT_FAILED)

    def test_alternate_base_urls(self):
        urls = self.services({f'/stats/{SID}': stats([1]), f'/learning/{SID}': learning([1])}, prefix='/kumite')
        env = {'KUMITE_BRAIN_URL': urls['brain'] + '/', 'KUMITE_REPLAY_URL': urls['replay'], 'KUMITE_ANALYTICS_URL': urls['analytics'] + '/'}
        resolved = check.resolve_urls(env)
        self.assertEqual(resolved['analytics'], urls['analytics'])
        report = self.run_check(resolved)
        self.assertEqual(report['exit_code'], check.EXIT_OK)
        self.assertEqual(check.resolve_urls({}), check.DEFAULTS)

    def test_display_url_hides_credentials(self):
        shown = check.display_url('http://kumite:secret@100.111.247.58:8765/base')
        self.assertEqual(shown, 'http://100.111.247.58:8765/base')
        self.assertNotIn('secret', shown)

    def test_unchanged_data_times_out_without_advance(self):
        started = time.monotonic()
        report = self.run_check(self.healthy(), watch_seconds=0.6, poll_seconds=0.1, require_advance=True)
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertFalse(report['advance']['advanced'])
        self.assertGreater(report['polls'], 0)
        self.assertEqual(report['exit_code'], check.EXIT_NO_ADVANCE)

    def test_missing_learning_is_incomplete_not_zero(self):
        report = self.run_check(self.healthy(learning_route=learning([])))
        self.assertEqual(report['learning']['status'], 'incomplete')
        self.assertIn('not a measured zero', report['learning']['detail'])
        self.assertEqual(report['exit_code'], check.EXIT_FAILED)

    def test_delayed_learning_catches_up(self):
        urls = self.healthy(learning_route=[learning([]), learning([]), learning([1, 2, 3, 4])])
        report = self.run_check(urls, watch_seconds=0.8, poll_seconds=0.1)
        self.assertEqual(report['learning']['status'], 'ok')
        self.assertEqual(report['exit_code'], check.EXIT_OK)

    def test_valid_round_advance_with_separate_flushes(self):
        urls = self.healthy(
            stats_route=[stats([1, 2, 3, 4]), stats([1, 2, 3, 4, 5])],
            learning_route=[learning([1, 2, 3, 4]), learning([1, 2, 3, 4]), learning([1, 2, 3, 4]), learning([1, 2, 3, 4, 5])]
        )
        report = self.run_check(urls, watch_seconds=2.0, poll_seconds=0.1, require_advance=True)
        self.assertTrue(report['advance']['advanced'])
        self.assertEqual(report['advance']['reached'], {'stats': 5, 'learning': 5})
        self.assertEqual(report['exit_code'], check.EXIT_OK)

    def test_reset_and_session_mismatch_do_not_count(self):
        urls = self.healthy(
            stats_route=[stats([1, 2, 3, 4]), stats([1]), stats([1, 2])],
            learning_route=[learning([1, 2, 3, 4]), learning([1, 2, 3, 4, 5], sid='another-session'), learning([1, 2, 3, 4])]
        )
        report = self.run_check(urls, watch_seconds=0.6, poll_seconds=0.1, require_advance=True)
        self.assertFalse(report['advance']['advanced'])
        self.assertEqual(report['advance']['reached'], {'stats': None, 'learning': None})
        self.assertTrue(any('went back' in reset for reset in report['advance']['resets']))
        self.assertEqual(report['exit_code'], check.EXIT_NO_ADVANCE)

    def test_reset_after_partial_advance_does_not_count(self):
        urls = self.healthy(
            stats_route=[stats([1, 2, 3, 4]), stats([1, 2, 3, 4, 5]), stats([1, 2, 3, 4])],
            learning_route=[learning([1, 2, 3, 4]), learning([1, 2, 3, 4]), learning([1, 2, 3, 4, 5])]
        )
        report = self.run_check(urls, watch_seconds=0.6, poll_seconds=0.1, require_advance=True)
        self.assertFalse(report['advance']['advanced'])
        self.assertEqual(report['advance']['reached'], {'stats': None, 'learning': 5})
        self.assertTrue(any('stats went back from round 5 to 4' in reset for reset in report['advance']['resets']))
        self.assertEqual(report['exit_code'], check.EXIT_NO_ADVANCE)

    def test_request_timeout_is_bounded(self):
        urls = self.healthy(stats_route=(200, stats([1]), 1.5))
        started = time.monotonic()
        report = self.run_check(urls, timeout_seconds=0.3)
        self.assertLess(time.monotonic() - started, 1.4)
        self.assertEqual(report['stats']['status'], 'unreachable')
        self.assertEqual(report['exit_code'], check.EXIT_FAILED)

    def test_main_prints_json_and_returns_exit_code(self):
        urls = self.healthy()
        env = {'KUMITE_BRAIN_URL': urls['brain'], 'KUMITE_REPLAY_URL': urls['replay'], 'KUMITE_ANALYTICS_URL': urls['analytics']}
        out = io.StringIO()
        code = check.main(['--session-id', SID, '--json', '--timeout-seconds', '2'], env=env, out=out)
        report = json.loads(out.getvalue())
        self.assertEqual(code, check.EXIT_OK)
        self.assertEqual(report['exit_code'], check.EXIT_OK)
        self.assertEqual(report['session_id'], SID)

    def test_require_advance_needs_a_watch_window(self):
        with self.assertRaises(SystemExit) as raised, mock.patch('sys.stderr', io.StringIO()):
            check.parse(['--session-id', SID, '--require-advance'])
        self.assertEqual(raised.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
