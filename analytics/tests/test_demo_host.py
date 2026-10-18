import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analytics import demo_host as host
from analytics.insight_examples import event, example, learning, round_end
from analytics.repository import FileRepository


class DemoHostTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sid = 'insight-example'
        example(self.root, [event(1, hit_level='low', damage=10), round_end(1)])
        self.requests = []

    def json(self, base, path, timeout):
        self.requests.append((base, path))
        if path == '/health':
            return {'ok': True, 'service': base, 'version': 'test'}
        if path == '/sessions/' + self.sid:
            return json.loads((self.root / 'sessions' / f'{self.sid}.json').read_text())
        repository = FileRepository(self.root)
        return repository.stats(self.sid) if path.startswith('/stats/') else repository.learning(self.sid)

    def run_check(self, digest=None, json_read=None):
        with patch.object(host, 'remote_json', side_effect=json_read or self.json), patch.object(host, 'remote_digest', side_effect=digest or (lambda *args: hashlib.sha256((self.root / 'recordings' / f'{self.sid}.jsonl').read_bytes()).hexdigest())):
            return host.inspect(self.root, self.sid, 'http://brain', 'http://analytics')

    def test_matching_canonical_source_is_a_snapshot_not_advancement(self):
        def read(base, path, timeout):
            return self.json(base.removeprefix('http://'), path, timeout)
        value = self.run_check(json_read=read)
        self.assertEqual(value['exit_code'], 0)
        self.assertEqual(value['mode'], 'source_snapshot')
        self.assertTrue(all(value['checks'].values()))
        self.assertEqual(value['recording_prefix']['local_sha256'], value['recording_prefix']['brain_sha256'])
        self.assertEqual(value['freshness']['completed_rounds'], [1])

    def test_same_session_name_with_different_brain_content_fails(self):
        value = self.run_check(digest=lambda *args: '0' * 64,
                               json_read=lambda base, path, timeout: self.json(base.removeprefix('http://'), path, timeout))
        self.assertEqual(value['exit_code'], 1)
        self.assertFalse(value['checks']['brain_recording_prefix'])

    def test_stale_or_wrong_analytics_and_wrong_service_identity_fail(self):
        def read(base, path, timeout):
            value = self.json(base.removeprefix('http://'), path, timeout)
            if path.startswith('/stats/'):
                value['totals']['low_block_rate'] = .5
            if base == 'http://analytics' and path == '/health':
                value['service'] = 'brain'
            return value
        value = self.run_check(json_read=read)
        self.assertEqual(value['exit_code'], 1)
        self.assertFalse(value['checks']['analytics_stats_match_local'])
        self.assertFalse(value['checks']['analytics_health_identity'])

    def test_delayed_learning_is_incomplete_then_current(self):
        recording = self.root / 'recordings' / f'{self.sid}.jsonl'
        with recording.open('a') as stream:
            stream.write(json.dumps(round_end(2)) + '\n')
        read = lambda base, path, timeout: self.json(base.removeprefix('http://'), path, timeout)
        value = self.run_check(json_read=read)
        self.assertEqual(value['exit_code'], 2)
        self.assertEqual(value['freshness']['pending_learning_rounds'], [2])
        with (self.root / 'learning' / f'{self.sid}.jsonl').open('a') as stream:
            stream.write(json.dumps(learning(2)) + '\n')
        self.assertEqual(self.run_check(json_read=read)['exit_code'], 0)

    def test_appending_source_with_a_wrong_brain_prefix_still_fails(self):
        def digest(*args):
            with (self.root / 'recordings' / f'{self.sid}.jsonl').open('a') as stream:
                stream.write(json.dumps(event(20, hit_level='low')) + '\n')
            return '0' * 64
        value = self.run_check(digest=digest, json_read=lambda base, path, timeout: self.json(base.removeprefix('http://'), path, timeout))
        self.assertEqual(value['exit_code'], 1)
        self.assertFalse(value['checks']['brain_recording_prefix'])

    def test_live_append_during_check_compares_completed_rounds(self):
        recording = self.root / 'recordings' / f'{self.sid}.jsonl'
        def read(base, path, timeout):
            if path.startswith('/stats/'):
                with recording.open('a') as stream:
                    stream.write(json.dumps(event(30, hit_level='low', round_=2, damage=10)) + '\n')
            return self.json(base.removeprefix('http://'), path, timeout)
        value = self.run_check(json_read=read)
        self.assertEqual(value['exit_code'], 0, value)
        self.assertEqual(value['comparison'], 'completed_rounds_while_appending')
        self.assertTrue(all(value['checks'].values()))

    def test_static_source_keeps_exact_comparison(self):
        value = self.run_check(json_read=lambda base, path, timeout: self.json(base.removeprefix('http://'), path, timeout))
        self.assertEqual(value['comparison'], 'exact')

    def test_wrong_completed_round_while_appending_fails(self):
        recording = self.root / 'recordings' / f'{self.sid}.jsonl'
        def read(base, path, timeout):
            value = self.json(base.removeprefix('http://'), path, timeout)
            if path.startswith('/stats/'):
                with recording.open('a') as stream:
                    stream.write(json.dumps(event(30, round_=2)) + '\n')
                value['rounds'][0]['low_block_rate'] = .5
            return value
        value = self.run_check(json_read=read)
        self.assertEqual(value['exit_code'], 1)
        self.assertFalse(value['checks']['analytics_stats_match_local'])

    def test_rewritten_source_during_check_retries_and_fails_without_false_parity(self):
        recording = self.root / 'recordings' / f'{self.sid}.jsonl'
        def read(base, path, timeout):
            if path.startswith('/learning/'):
                content = recording.read_bytes()
                flipped = content.replace(b'"damage": 10', b'"damage": 12', 1) if b'"damage": 10' in content else content.replace(b'"damage": 12', b'"damage": 10', 1)
                recording.write_bytes(flipped + json.dumps(event(40, round_=2)).encode() + b'\n')
            return self.json(base.removeprefix('http://'), path, timeout)
        value = self.run_check(json_read=read)
        self.assertEqual(value['exit_code'], 1)
        self.assertIn('changing', value['error'])

    def test_path_validation_and_metadata_reference_do_not_redirect_data(self):
        for bad in ('relative/data', str(self.root / 'missing')):
            with self.subTest(path=bad), self.assertRaises((OSError, ValueError)):
                host.data_root(bad)
        meta = self.root / 'sessions' / f'{self.sid}.json'
        value = json.loads(meta.read_text())
        value['recording'] = str(self.root / 'other.jsonl')
        meta.write_text(json.dumps(value))
        with patch.object(host, 'remote_json') as remote:
            result = host.inspect(self.root, self.sid, 'http://brain', 'http://analytics')
        self.assertEqual(result['exit_code'], 1)
        remote.assert_not_called()

    def test_relative_recorder_reference_resolves_to_the_selected_folder_from_any_checkout(self):
        meta = self.root / 'sessions' / f'{self.sid}.json'
        value = json.loads(meta.read_text())
        value['recording'] = f'data/recordings/{self.sid}.jsonl'
        meta.write_text(json.dumps(value))
        result = self.run_check(json_read=lambda base, path, timeout: self.json(base.removeprefix('http://'), path, timeout))
        self.assertEqual(result['exit_code'], 0)
        self.assertTrue(all(result['checks'].values()))

    def test_latest_session_uses_brain_ordering(self):
        for sid, started in (('older-set', '2026-10-17T00:00:00Z'), ('newest-set', '2026-10-19T00:00:00Z')):
            value = json.loads((self.root / 'sessions' / f'{self.sid}.json').read_text())
            value.update(session_id=sid, started_at=started)
            (self.root / 'sessions' / f'{sid}.json').write_text(json.dumps(value))
        (self.root / 'sessions' / 'broken.json').write_text('{')
        self.assertEqual(host.latest_session(self.root), 'newest-set')

    def observe(self, on_sleep=None):
        read = lambda base, path, timeout: self.json(base.removeprefix('http://'), path, timeout)
        digest = lambda *args: hashlib.sha256((self.root / 'recordings' / f'{self.sid}.jsonl').read_bytes()).hexdigest()
        now = [0.0]
        def sleep(seconds):
            now[0] += seconds
            if on_sleep:
                on_sleep(now[0])
        with patch.object(host, 'remote_json', side_effect=read), patch.object(host, 'remote_digest', side_effect=digest):
            return host.observe(self.root, self.sid, 'http://brain', 'http://analytics', 2, 10, clock=lambda: now[0], sleep=sleep)

    def test_before_after_mode_waits_for_a_later_completed_round_with_learning(self):
        def flush(now):
            if now == 2:
                with (self.root / 'recordings' / f'{self.sid}.jsonl').open('a') as stream:
                    stream.write(json.dumps(round_end(2)) + '\n')
            if now == 4:
                with (self.root / 'learning' / f'{self.sid}.jsonl').open('a') as stream:
                    stream.write(json.dumps(learning(2)) + '\n')
        value = self.observe(flush)
        self.assertEqual(value['exit_code'], 0)
        self.assertTrue(value['advanced'])
        self.assertEqual(value['before']['freshness']['completed_rounds'], [1])
        self.assertEqual(value['after']['freshness']['completed_rounds'], [1, 2])
        self.assertNotEqual(value['before']['snapshot_id'], value['after']['snapshot_id'])

    def test_before_after_mode_without_a_new_round_is_exit_2(self):
        value = self.observe()
        self.assertEqual(value['exit_code'], 2)
        self.assertFalse(value['advanced'])
        self.assertEqual(value['after']['exit_code'], 0)

    def test_before_after_mode_stops_on_a_failed_first_check(self):
        with patch.object(host, 'remote_json', side_effect=OSError('down')):
            value = host.observe(self.root, self.sid, 'http://brain', 'http://analytics', 2, 10, clock=lambda: 0, sleep=lambda s: None)
        self.assertEqual(value['exit_code'], 1)
        self.assertIsNone(value['after'])

    def test_http_reads_are_get_only_and_diagnostics_hide_server_bodies(self):
        requests = []
        def urlopen(request, timeout):
            requests.append(request)
            return io.BytesIO(b'{"ok":true}')
        with patch.object(host.urllib.request, 'urlopen', side_effect=urlopen):
            self.assertEqual(host.remote_json('http://host', '/health', 2), {'ok': True})
            self.assertEqual(host.remote_digest('http://host', '/recording', 3, 2), hashlib.sha256(b'{"o').hexdigest())
        self.assertTrue(all(request.get_method() == 'GET' for request in requests))
        with self.assertRaises(ValueError):
            host.service_url('http://user:private-token@host')
        def unavailable(*args):
            raise OSError('private-token')
        result = self.run_check(json_read=unavailable)
        self.assertNotIn('private-token', json.dumps(result))

    def test_launcher_sets_absolute_root_before_start_and_can_disable_database(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'invalid-for-test'}), patch('uvicorn.run') as run:
            host.serve(self.root, '127.0.0.1', 8767, file_only=True)
            self.assertEqual(os.environ['DATA_DIR'], str(self.root.resolve()))
            self.assertEqual(os.environ['DATABASE_URL'], '')
            run.assert_called_once_with('analytics.main:app', host='127.0.0.1', port=8767)

    def test_invalid_finite_timeout_and_session_id_are_rejected_before_requests(self):
        for option in ('nan', 'inf', '0', '31'):
            with self.subTest(timeout=option), self.assertRaises(SystemExit), patch('sys.stderr', io.StringIO()):
                host.main(['check', '--data-dir', str(self.root), '--session-id', self.sid, '--timeout-seconds', option])
        with self.assertRaises(ValueError):
            host.inspect(self.root, '../bad', 'http://brain', 'http://analytics')
        for option in ('-1', '901'):
            with self.subTest(wait=option), self.assertRaises(SystemExit), patch('sys.stderr', io.StringIO()):
                host.main(['check', '--data-dir', str(self.root), '--session-id', 'latest', '--wait-for-round-seconds', option])


if __name__ == '__main__':
    unittest.main()
