import importlib.util
import json
import unittest
from collections import Counter
from pathlib import Path

from game.summarize import check_session, event_key, find_session, load_jsonl, replay
from game.tests.test_state import EVENT_V, STATE_V

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"
PRACTICE = SAMPLES / "practice_djin_vs_kaz.jsonl"
VERSUS = SAMPLES / "versus_djin_vs_kaz_l3.zip"
NEUTRAL = SAMPLES / "versus_djin_vs_kaz_l3_neutral.zip"
LIVE = SAMPLES / "live_learning"
LIVE_SID = "2026-10-18T05-14-03_sahil_djin_vs_kaz"
STATE_STRIDE = 25


def contracts_validate():
    spec = importlib.util.spec_from_file_location("kumite_validate_samples", SAMPLES.parents[1] / "contracts" / "validate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        replayed = [e for e in replay(states, meta["mode"]) if e["kind"] != "decision_point"]
        recorded = [e for e in events if e["kind"] != "decision_point"]
        self.assertEqual(Counter(event_key(e) for e in replayed), Counter(event_key(e) for e in recorded))
        again = [e for e in replay(states, meta["mode"]) if e["kind"] == "decision_point"]
        first = [e for e in replay(states, meta["mode"]) if e["kind"] == "decision_point"]
        self.assertEqual(Counter(event_key(e) for e in again), Counter(event_key(e) for e in first))

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

    def test_neutral_sample(self):
        meta, states, events, tactical = self.load(NEUTRAL)
        self.check_contract(states, events)
        self.check_replay(meta, states, events)
        self.assertEqual((meta["mode"], meta["difficulty"], meta["result"]), ("versus", 3, "win 3-1"))
        self.assertEqual([r["winner"] for r in meta["rounds"]], [0, 0, 1, 0])
        decisions = [e for e in events if e["kind"] == "decision_point"]
        situations = Counter(e["situation"] for e in decisions)
        self.assertEqual(situations["low_defense"], 13)
        self.assertEqual(situations["throw_break"], 9)
        self.assertGreater(sum(n for s, n in situations.items() if s.startswith("after_block:")), 5)
        self.assertTrue(all(e["actor"] == meta["human_slot"] and e["detail"]["state_text"] for e in decisions))
        sources = Counter(t["source"] for t in tactical)
        self.assertGreater(sources["default"], 100)
        self.assertGreater(sources["reflex"], 50)
        mix = Counter(t["chosen"] for t in tactical if t["source"] == "default")
        for option in ("mid", "low", "throw", "approach"):
            self.assertGreater(mix[option], 0, option)

    def test_live_learning_sample(self):
        sid = LIVE_SID
        records = load_jsonl(LIVE / "recordings" / f"{sid}.jsonl")
        states = [r for r in records if r["t"] == "state"]
        events = [r for r in records if r["t"] == "event"]
        meta = json.loads((LIVE / "sessions" / f"{sid}.json").read_text(encoding="utf-8"))
        self.assertEqual(check_session(json.dumps(meta))[1], [])
        self.assertEqual(meta["recording"], f"data/samples/live_learning/recordings/{sid}.jsonl")
        self.assertEqual((meta["mode"], meta["difficulty"], meta["result"]), ("versus", 3, "loss 1-3"))
        self.check_contract(states, events)
        self.check_replay(meta, states, events)
        module = contracts_validate()
        schemas = module.load_schemas()
        self.assertEqual(module.check_jsonl(schemas, LIVE / "recordings" / f"{sid}.jsonl"), 0)
        self.assertEqual(module.check_jsonl(schemas, LIVE / "learning" / f"{sid}.jsonl"), 0)
        profile = json.loads((LIVE / "profiles" / "sahil_devil_jin.json").read_text(encoding="utf-8"))
        self.assertEqual(list(module.validator(schemas, "profile").iter_errors(profile)), [])
        summaries = [r for r in records if r["t"] == "round_summary"]
        self.assertEqual([s["round"] for s in summaries], [1, 2, 3, 4])
        self.assertEqual([s["winner"] for s in summaries], [r["winner"] for r in meta["rounds"]])
        lows = Counter(e["action"] for e in events if e["kind"] == "decision_point" and e["situation"] == "low_defense")
        self.assertEqual(lows, Counter({"hit": 16}))
        learning = [json.loads(x) for x in (LIVE / "learning" / f"{sid}.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        self.assertEqual([r["round"] for r in learning], [1, 2, 3, 4])
        self.assertNotIn("low_defense", learning[0]["habits"])
        self.assertEqual(learning[-1]["habits"]["low_defense"]["action"], "hit")
        self.assertFalse(learning[-1]["habits"]["low_defense"]["fixed"])
        tactical = [r for r in records if r["t"] == "tactical" and r.get("source") in ("default", "habit")]
        weight = {rnd: [r["tactical"]["weights"]["low"] for r in tactical if r["round"] == rnd] for rnd in (1, 2, 3, 4)}
        mean = {rnd: sum(w) / len(w) for rnd, w in weight.items()}
        self.assertGreater(mean[3], mean[2] * 1.5)
        self.assertGreater(mean[4], mean[1] * 1.5)
        habit_lows = Counter(r["round"] for r in tactical if r["source"] == "habit" and r["chosen"] == "low")
        self.assertEqual((habit_lows[1], habit_lows[2]), (0, 0))
        self.assertGreater(habit_lows[4], 10)
        events_ = [(r["event"], r["situation"]) for r in records if r["t"] == "learning_event"]
        self.assertEqual(events_, [("fixed", "after_block:any"), ("regressed", "after_block:any")])


if __name__ == "__main__":
    unittest.main()
