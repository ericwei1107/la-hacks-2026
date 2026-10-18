import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch

os.environ['SENTRY_DSN'] = ''

from fastapi.testclient import TestClient

from analytics import insights
from analytics.insight_examples import PUBLIC_FIXTURES, REAL_ID
from analytics.insights import PUBLIC_VALIDATOR, InsightRepository, public
from analytics.main import create_app
from analytics.repository import ROOT, DataError

REAL = ROOT / 'data/samples/live_learning'
SYNTHETIC = ROOT / 'data/samples/synthetic'
SYNTHETIC_ID = '2026-10-17T13-05-00_synth_djin_vs_kaz'


class InsightsRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, {'DATABASE_URL': ''}):
            cls.on = TestClient(create_app(REAL, experimental_insights=True))
            cls.off = TestClient(create_app(REAL, experimental_insights=False))
        cls.expected = public(InsightRepository(REAL).snapshot(REAL_ID, insights.PUBLIC_LIMIT))

    def test_route_is_absent_unless_enabled(self):
        self.assertEqual(self.off.get(f'/insights/{REAL_ID}').status_code, 404)
        with patch.dict(os.environ, {'DATABASE_URL': '', 'KUMITE_EXPERIMENTAL_INSIGHTS': '1'}):
            enabled = TestClient(create_app(REAL))
        self.assertEqual(enabled.get(f'/insights/{REAL_ID}').status_code, 200)
        with patch.dict(os.environ, {'DATABASE_URL': '', 'KUMITE_EXPERIMENTAL_INSIGHTS': '0'}):
            disabled = TestClient(create_app(REAL))
        self.assertEqual(disabled.get(f'/insights/{REAL_ID}').status_code, 404)

    def test_enabled_route_returns_the_schema_valid_public_view(self):
        response = self.on.get(f'/insights/{REAL_ID}')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(list(PUBLIC_VALIDATOR.iter_errors(body)), [])
        self.assertEqual(body, self.expected)
        self.assertEqual([(m['successes'], m['opportunities']) for m in body['metrics'].values()], [(0, 16), (1, 4), (1, 5)])
        self.assertEqual(body['focus']['metric'], 'low_defense')
        self.assertLessEqual(len(body['moments']), 5)
        self.assertEqual(body, json.loads((PUBLIC_FIXTURES / 'real.json').read_text()))

    def test_limit_changes_moments_but_not_counts(self):
        body = self.on.get(f'/insights/{REAL_ID}?limit=2').json()
        self.assertEqual(len(body['moments']), 2)
        counts = lambda view: {key: (m['successes'], m['opportunities'], m['failures'], m['state'], m['evidence_total']) for key, m in view['metrics'].items()}
        self.assertEqual(counts(body), counts(self.expected))
        self.assertTrue(all(len(m['evidence']) <= 2 for m in body['metrics'].values()))
        self.assertEqual(body['moments_total'], self.expected['moments_total'])

    def test_errors_are_bounded(self):
        self.assertEqual(self.on.get('/insights/unknown-session').status_code, 404)
        for query in ('?limit=0', '?limit=51', '?limit=many'):
            with self.subTest(query=query):
                self.assertEqual(self.on.get(f'/insights/{REAL_ID}{query}').status_code, 422)
        self.assertEqual(self.on.get('/insights/bad%20id').status_code, 422)
        with patch.object(InsightRepository, 'snapshot', side_effect=DataError('/private/path secret-token')):
            response = self.on.get(f'/insights/{REAL_ID}')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('secret-token', response.text)
        self.assertNotIn('/private/path', response.text)

    def test_existing_routes_are_unchanged_by_the_flag(self):
        for path in (f'/stats/{REAL_ID}', f'/learning/{REAL_ID}', '/trends/sahil/devil_jin', '/health'):
            with self.subTest(path=path):
                self.assertEqual(self.on.get(path).json(), self.off.get(path).json())

    def synthetic_copy(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / 'data'
        shutil.copytree(SYNTHETIC, root)
        meta = root / 'sessions' / f'{SYNTHETIC_ID}.json'
        value = json.loads(meta.read_text())
        value['recording'] = str(root / 'recordings' / f'{SYNTHETIC_ID}.jsonl')
        meta.write_text(json.dumps(value))
        return root, meta

    def client(self, root):
        with patch.dict(os.environ, {'DATABASE_URL': ''}):
            return TestClient(create_app(root, experimental_insights=True))

    def test_route_reads_only_brain_files_under_data_dir(self):
        root, _ = self.synthetic_copy()
        (root / 'reports').mkdir()
        (root / 'reports' / f'{SYNTHETIC_ID}.json').write_text('{"not": "read"}')
        opened = []
        original = insights.read_bytes
        def spy(path, optional=False):
            opened.append(Path(path).resolve())
            return original(path, optional)
        with patch.object(insights, 'read_bytes', side_effect=spy):
            response = self.client(root).get(f'/insights/{SYNTHETIC_ID}')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('report', response.json())
        self.assertTrue(opened)
        self.assertTrue(all(path.is_relative_to(root.resolve()) for path in opened), opened)
        self.assertEqual({path.parent.name for path in opened} - {'sessions', 'recordings', 'learning', 'eval'}, set())
        internal = InsightRepository(root).snapshot(SYNTHETIC_ID, 5)
        self.assertEqual(internal['report']['status'], 'invalid')

    def test_route_refuses_a_recording_outside_data_dir(self):
        root, meta = self.synthetic_copy()
        value = json.loads(meta.read_text())
        value['recording'] = str(SYNTHETIC / 'recordings' / f'{SYNTHETIC_ID}.jsonl')
        meta.write_text(json.dumps(value))
        (root / 'recordings' / f'{SYNTHETIC_ID}.jsonl').unlink()
        response = self.client(root).get(f'/insights/{SYNTHETIC_ID}')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(str(SYNTHETIC), response.text)

    def test_cli_public_output_matches_the_route(self):
        out = io.StringIO()
        with redirect_stdout(out):
            insights.main([REAL_ID, '--data-dir', str(REAL), '--limit', str(insights.PUBLIC_LIMIT), '--public'])
        self.assertEqual(json.loads(out.getvalue()), self.expected)


if __name__ == '__main__':
    unittest.main()
