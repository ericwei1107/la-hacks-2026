import json
import unittest
from collections import Counter
from pathlib import Path

from game.summarize import check_session, event_key, find_session, load_jsonl, replay
from game.tests.test_state import EVENT_V, STATE_V

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"
PRACTICE = SAMPLES / "practice_djin_vs_kaz.jsonl"
VERSUS = SAMPLES / "versus_djin_vs_kaz_l3.zip"
STATE_STRIDE = 25


class SampleTest(unittest.TestCase):
    def load(self, path):
        records = load_jsonl(path)
        states = [r for r in records if r["t"] == "state"]
        events = [r for r in records if r["t"] == "event"]
        tactical = [r for r in records if r["t"] == "tactical"]
        label, text = find_session(path, states[0]["session_id"])
        meta, errors = check_session(text)
        self.assertEqual(errors, [], label)
        return meta, states, events, tactical

    def check_contract(self, states, events):
        for s in states[::STATE_STRIDE]:
            self.assertEqual([e.message for e in STATE_V.iter_errors(s)], [], f"state r{s['round']} f{s['frame']}")
        for ev in events:
            self.assertEqual([e.message for e in EVENT_V.iter_errors(ev)], [], f"event {ev}")

    def check_replay(self, meta, states, events):
        has_decisions = any(e["kind"] == "decision_point" for e in events)
        replayed = [e for e in replay(states, meta["mode"]) if has_decisions or e["kind"] != "decision_point"]
        self.assertEqual(Counter(event_key(e) for e in replayed), Counter(event_key(e) for e in events))

    def test_practice_sample(self):
        meta, states, events, _ = self.load(PRACTICE)
        self.check_contract(states, events)
        self.check_replay(meta, states, events)

    def test_versus_sample(self):
        meta, states, events, tactical = self.load(VERSUS)
        self.check_contract(states, events)
        self.check_replay(meta, states, events)
        self.assertEqual(meta["mode"], "versus")
        self.assertEqual(meta["result"], "loss 1-3")
        self.assertEqual([r["winner"] for r in meta["rounds"]], [0, 1, 1, 1])
        ends = [e["detail"]["reason"] for e in events if e["kind"] == "round_end"]
        self.assertEqual(ends, ["ko", "time", "time", "ko"])
        kinds = Counter(e["kind"] for e in events)
        for kind in ("throw_break", "whiff", "knockdown", "block", "hit"):
            self.assertGreater(kinds[kind], 0, kind)
        reflex = Counter(t["reflex"]["kind"] for t in tactical)
        for kind in ("block", "punish", "throw_break", "wakeup"):
            self.assertGreater(reflex[kind], 0, kind)
        self.assertTrue(all(t["source"] == "reflex" for t in tactical))


if __name__ == "__main__":
    unittest.main()
