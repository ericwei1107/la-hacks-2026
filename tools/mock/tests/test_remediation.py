import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import analytics_mock
from fastapi.testclient import TestClient
from analytics.repository import FileRepository
from store import ROOT, Store, load_jsonl
from serve import shutdown_signals


class MockRemediationTest(unittest.TestCase):
    def test_mock_file_trends_learning_and_evaluation_parity(self):
        fixture = ROOT / 'tools/mock/tests/fixtures/two-rounds.jsonl'
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'DATA_DIR': directory}):
            root = Path(directory)
            samples = root / 'samples'
            samples.mkdir()
            path = samples / fixture.name
            path.write_bytes(fixture.read_bytes())
            path.with_suffix('.session.json').write_bytes(fixture.with_suffix('.session.json').read_bytes())
            store = Store([path])
            session = store.default()
            client = TestClient(analytics_mock.create(store))
            files = FileRepository(root)
            (root / 'learning').mkdir()
            records = [{'t': 'learning_round', 'session_id': session.id, 'round': 1, 'prediction_accuracy': 0.4, 'habits': {'low_defense': {'p': 0.8, 'n': 4}}}, {'t': 'learning_round', 'round': 2, 'prediction_accuracy': 0.7, 'habits': {}}]
            (root / 'learning' / f'{session.id}.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in [records[1], records[0], {**records[0], 'prediction_accuracy': 0.6}]))
            (root / 'eval').mkdir()
            evaluation = root / 'eval' / f'{session.id}.json'
            evaluation.write_text('{"before":0.4,"after":0.7}')
            with patch.object(type(session), 'load_learning', return_value=[records[1], records[0], {**records[0], 'prediction_accuracy': 0.6}]):
                self.assertEqual(client.get(f'/learning/{session.id}').json(), files.learning(session.id))
            self.assertEqual(client.get('/trends/fixture/devil_jin').json(), files.trends('fixture', 'devil_jin'))
            self.assertEqual(client.get('/trends/fixture/devil_jin?stat=').json(), files.trends('fixture', 'devil_jin', ''))
            for bad in ('{"before":true,"after":0.7}', '{"before":-1,"after":0.7}', '{bad'):
                evaluation.write_text(bad)
                self.assertEqual(client.get(f'/learning/{session.id}').status_code, 503)
            evaluation.unlink()
            self.assertEqual(client.get(f'/learning/{session.id}').json()['finetune'], {'before': None, 'after': None})
            (root / 'learning' / f'{session.id}.jsonl').write_text('{broken\n')
            self.assertEqual(client.get(f'/learning/{session.id}').status_code, 503)

    def test_bad_metadata_does_not_hide_a_healthy_discovered_session(self):
        fixture = ROOT / 'tools/mock/tests/fixtures/two-rounds.jsonl'
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'DATA_DIR': directory}):
            root = Path(directory)
            samples = root / 'samples'
            samples.mkdir()
            (samples / fixture.name).write_bytes(fixture.read_bytes())
            (samples / fixture.with_suffix('.session.json').name).write_bytes(fixture.with_suffix('.session.json').read_bytes())
            (root / 'sessions').mkdir()
            (root / 'sessions/broken.json').write_text('{"recording":123}')
            client = TestClient(analytics_mock.create(Store()))
            self.assertEqual(client.get('/stats/fixture-two-rounds').status_code, 200)
            self.assertEqual(client.get('/stats/broken').status_code, 503)

    def test_windows_signal_fallback_restores_previous_handlers(self):
        loop, stop = MagicMock(), MagicMock()
        loop.add_signal_handler.side_effect = NotImplementedError
        previous = object()
        with patch('serve.signal.getsignal', return_value=previous), patch('serve.signal.signal') as install:
            with shutdown_signals(loop, stop):
                self.assertEqual(install.call_count, 2)
                install.call_args_list[0].args[1](2, None)
                loop.call_soon_threadsafe.assert_called_once_with(stop.set)
            self.assertEqual(install.call_count, 4)
            self.assertIs(install.call_args.args[1], previous)
            loop.remove_signal_handler.assert_not_called()

    def test_posix_handlers_are_removed_even_on_failure(self):
        loop = MagicMock()
        with self.assertRaises(RuntimeError):
            with shutdown_signals(loop, MagicMock()):
                raise RuntimeError('startup failed')
        self.assertEqual(loop.add_signal_handler.call_count, 2)
        self.assertEqual(loop.remove_signal_handler.call_count, 2)

    def test_partial_tokens_are_tolerated_by_mock_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'partial.jsonl'
            path.write_text('{"t":"future","value":tru')
            self.assertEqual(load_jsonl(path), [])


if __name__ == '__main__':
    unittest.main()
