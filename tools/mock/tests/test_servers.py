import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import analytics
import brain
import replay
from store import ROOT, Store, check

SAMPLE = ROOT / "data" / "samples" / "practice_djin_vs_kaz.jsonl"


class ServersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        os.environ["DATA_DIR"] = cls.tmp
        cls.store = Store([SAMPLE])
        cls.sid = next(iter(cls.store.sessions))
        cls.brain = TestClient(brain.create(cls.store, rate=600))
        cls.replay = TestClient(replay.create(cls.store))
        cls.analytics = TestClient(analytics.create(cls.store))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        os.environ.pop("DATA_DIR", None)

    def ok(self, response, schema=None, sub=None):
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        if schema:
            self.assertEqual(check(schema, body, sub), [])
        return body

    def test_health(self):
        for client, name in ((self.brain, "brain"), (self.replay, "replay"), (self.analytics, "analytics")):
            body = self.ok(client.get("/health"))
            self.assertTrue(body["ok"])
            self.assertEqual(body["service"], name)

    def test_sessions(self):
        listed = self.ok(self.brain.get("/sessions"))
        self.assertIn(self.sid, [s["session_id"] for s in listed])
        for s in listed:
            self.assertEqual(check("session", s), [])
        self.ok(self.brain.get(f"/sessions/{self.sid}"), "session")
        self.assertEqual(self.brain.get("/sessions/nope").status_code, 404)

    def test_recording(self):
        r = self.brain.get(f"/sessions/{self.sid}/recording")
        self.assertEqual(r.status_code, 200)
        self.assertIn("application/x-ndjson", r.headers["content-type"])
        self.assertGreater(len(r.text.splitlines()), 100)

    def test_profiles(self):
        for p in self.ok(self.brain.get("/profiles/sahil")):
            self.assertEqual(check("profile", p), [])

    def test_config(self):
        self.ok(self.brain.get("/config"), "config")
        merged = self.ok(self.brain.post("/config", json={"difficulty": 4, "knobs": {"exploit_weight": 0.5}}), "config")
        self.assertEqual(merged["difficulty"], 4)
        self.assertEqual(merged["knobs"]["exploit_weight"], 0.5)
        self.assertIn("reaction_delay_frames", merged["knobs"])
        self.assertEqual(self.brain.post("/config", json={"difficulty": 9}).status_code, 422)

    def test_ws_state(self):
        seen = []
        with self.brain.websocket_connect("/ws/state") as ws:
            while len(seen) < 10:
                seen.append(json.loads(ws.receive_text()))
        for rec in seen:
            self.assertIn(rec["t"], ("state", "event"))
            self.assertEqual(check("gamestate" if rec["t"] == "state" else "event", rec), [])

    def test_ws_coach(self):
        with self.brain.websocket_connect("/ws/coach") as ws:
            summary = json.loads(ws.receive_text())
            coach = json.loads(ws.receive_text())
        self.assertEqual(check("round_summary", summary), [])
        self.assertEqual(coach["t"], "coach")
        self.assertIn(coach["severity"], ("info", "warn", "praise"))

    def test_coach_round(self):
        example = json.loads((ROOT / "contracts" / "examples" / "round_summary.json").read_text())
        body = self.ok(self.replay.post("/coach/round", json=example))
        self.assertLess(len(body["text"].split()), 40)
        self.assertEqual(self.replay.post("/coach/round", json={"t": "round_summary"}).status_code, 422)

    def test_analyze_and_report(self):
        self.assertEqual(self.replay.get(f"/reports/{self.sid}").status_code, 404)
        self.ok(self.replay.post(f"/analyze/{self.sid}"), "report")
        self.ok(self.replay.get(f"/reports/{self.sid}"), "report")
        self.assertTrue((Path(self.tmp) / "reports" / f"{self.sid}.json").exists())

    def test_chat(self):
        body = self.ok(self.replay.post("/coach/chat", json={"session_id": self.sid, "player": "sahil", "message": "what now?", "history": []}))
        self.assertIn("text", body)
        self.assertIsInstance(body["citations"], list)

    def test_stats(self):
        body = self.ok(self.analytics.get(f"/stats/{self.sid}"))
        self.assertEqual(body["session_id"], self.sid)
        for block in body["rounds"] + [body["totals"]]:
            for key in ("damage_taken_by_situation", "punish_rate", "throw_break_rate", "low_block_rate", "counter_hits_taken", "counter_hits_given", "avg_adv_after_block"):
                self.assertIn(key, block)

    def test_learning_and_trends(self):
        self.ok(self.analytics.get(f"/learning/{self.sid}"), "metrics")
        body = self.ok(self.analytics.get("/trends/sahil/devil_jin"))
        self.assertEqual(len(body["series"]), 1)

    def test_truncated_last_line(self):
        copy = Path(self.tmp) / "truncated.jsonl"
        lines = SAMPLE.read_text().splitlines()
        copy.write_text("\n".join(lines) + "\n" + lines[-1][: len(lines[-1]) // 2])
        s = Store([copy])
        self.assertEqual(len(next(iter(s.sessions.values())).records), len([l for l in lines if l.strip()]))


if __name__ == "__main__":
    unittest.main()
