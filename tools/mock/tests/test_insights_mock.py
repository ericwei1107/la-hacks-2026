import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['SENTRY_DSN'] = ''

from fastapi.testclient import TestClient

import analytics_mock
import serve
from store import ROOT, Store

REAL = ROOT / 'data' / 'samples' / 'live_learning'
SID = '2026-10-18T05-14-03_sahil_djin_vs_kaz'


class InsightsMockTest(unittest.TestCase):
    def test_flagged_mock_matches_real_analytics_and_default_has_no_route(self):
        with patch.dict(os.environ, {'DATA_DIR': str(REAL), 'DATABASE_URL': ''}):
            from analytics.main import create_app
            store = Store()
            mock = TestClient(analytics_mock.create(store, insights=True))
            plain = TestClient(analytics_mock.create(store))
            real = TestClient(create_app(REAL, experimental_insights=True))
            body = mock.get(f'/insights/{SID}')
            self.assertEqual(body.status_code, 200)
            self.assertEqual(body.json(), real.get(f'/insights/{SID}').json())
            self.assertEqual(mock.get(f'/insights/{SID}?limit=3').json(), real.get(f'/insights/{SID}?limit=3').json())
            self.assertEqual(plain.get(f'/insights/{SID}').status_code, 404)
            self.assertEqual(mock.get('/insights/unknown-session').status_code, 404)
            self.assertEqual(mock.get(f'/insights/{SID}?limit=0').status_code, 422)
            self.assertEqual(mock.get(f'/stats/{SID}').json(), plain.get(f'/stats/{SID}').json())

    def test_serve_flag_defaults_off(self):
        self.assertFalse(serve.parse([]).experimental_insights)
        self.assertTrue(serve.parse(['--experimental-insights']).experimental_insights)


if __name__ == '__main__':
    unittest.main()
