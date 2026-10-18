import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import synth
from store import CONTRACTS, Store

sys.path.insert(0, str(CONTRACTS))
from validate import check_jsonl, load_schemas


class SynthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        os.environ["DATA_DIR"] = str(cls.tmp)
        cls.sid = synth.generate(cls.tmp)
        cls.recording = cls.tmp / "recordings" / f"{cls.sid}.jsonl"
        cls.records = [json.loads(l) for l in cls.recording.read_text().splitlines()]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        os.environ.pop("DATA_DIR", None)

    def test_files_written(self):
        for path in (self.recording, self.tmp / "sessions" / f"{self.sid}.json", self.tmp / "learning" / f"{self.sid}.jsonl", self.tmp / "profiles" / "synth_devil_jin.json"):
            self.assertTrue(path.exists(), path)

    def test_contract_validator_passes(self):
        self.assertEqual(check_jsonl(load_schemas(), self.recording), 0)

    def test_deterministic(self):
        other = Path(tempfile.mkdtemp())
        try:
            synth.generate(other)
            for sub, ext in (("recordings", "jsonl"), ("learning", "jsonl")):
                self.assertEqual((other / sub / f"{self.sid}.{ext}").read_bytes(), (self.tmp / sub / f"{self.sid}.{ext}").read_bytes(), sub)
            a, b = (json.loads((d / "sessions" / f"{self.sid}.json").read_text()) for d in (other, self.tmp))
            a.pop("recording"), b.pop("recording")
            self.assertEqual(a, b)
        finally:
            shutil.rmtree(other, ignore_errors=True)

    def test_story(self):
        summaries = [r for r in self.records if r["t"] == "round_summary"]
        self.assertEqual([s["round"] for s in summaries], [1, 2, 3])
        self.assertEqual([s["winner"] for s in summaries], [1, 1, 0])
        self.assertIn("low_defense", summaries[0]["exploited"])
        self.assertEqual(summaries[2]["newly_fixed"], ["low_defense"])
        lows = [r for r in self.records if r["t"] == "event" and r.get("situation") == "low_defense" and r["kind"] in ("hit", "block")]
        per_round = {n: [e["kind"] for e in lows if e["round"] == n] for n in (1, 2, 3)}
        self.assertEqual(per_round[1].count("hit"), 4)
        self.assertEqual(per_round[2].count("hit"), 3)
        self.assertEqual(per_round[3].count("block"), 5)
        meta = json.loads((self.tmp / "sessions" / f"{self.sid}.json").read_text())
        self.assertEqual(meta["result"], "loss 1-2")
        self.assertEqual(meta["mode"], "synthetic")

    def test_frames_reset_each_round(self):
        for n in (1, 2, 3):
            frames = [r["frame"] for r in self.records if r["t"] == "state" and r["round"] == n]
            self.assertEqual(frames[0], 0)
            self.assertEqual(frames, list(range(len(frames))))

    def test_ensure_reuses(self):
        before = self.recording.stat().st_mtime_ns
        self.assertEqual(synth.ensure(self.tmp), self.sid)
        self.assertEqual(self.recording.stat().st_mtime_ns, before)

    def test_served_by_mock(self):
        from fastapi.testclient import TestClient
        import analytics_mock as analytics

        store = Store()
        self.assertIn(self.sid, store.sessions)
        client = TestClient(analytics.create(store))
        learning = client.get(f"/learning/{self.sid}").json()
        self.assertEqual(learning["time_to_detect"]["low_defense"], 1)
        self.assertEqual(learning["time_to_mastery"]["low_defense"], 3)
        self.assertEqual([r["prediction_accuracy"] for r in learning["rounds"]], [0.41, 0.58, 0.71])
        self.assertEqual(learning["finetune"], {"before": None, "after": None})
        (self.tmp / "eval").mkdir(exist_ok=True)
        (self.tmp / "eval" / f"{self.sid}.json").write_text(json.dumps({"before": 0.41, "after": 0.68}))
        try:
            self.assertEqual(client.get(f"/learning/{self.sid}").json()["finetune"], {"before": 0.41, "after": 0.68})
        finally:
            (self.tmp / "eval" / f"{self.sid}.json").unlink()
        stats = client.get(f"/stats/{self.sid}").json()
        self.assertEqual(stats["rounds"][0]["low_block_rate"], 0.2)
        self.assertEqual(stats["rounds"][2]["low_block_rate"], 1.0)
        self.assertEqual([r["throw_break_rate"] for r in stats["rounds"]], [0.5, None, 1.0])


if __name__ == "__main__":
    unittest.main()
