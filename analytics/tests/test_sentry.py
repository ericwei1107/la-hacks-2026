import json
import subprocess
import sys
import unittest
from pathlib import Path


class SentryInstrumentationTest(unittest.TestCase):
    def test_existing_initialization_captures_each_http_route(self):
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('_sentry_capture.py'))], cwd=root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['initializations'], 1)
        self.assertEqual(len(report['transactions']), 4)
        self.assertFalse(report['network_transport'])


if __name__ == '__main__':
    unittest.main()
