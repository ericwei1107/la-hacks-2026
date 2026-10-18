import json
import random
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from game.difficulty import Difficulty
from game.options import CLASSES, MOVEMENT_CLASSES, load_fallback, normalize_table
from game.reflex import Reflex, load_punishers
from game.replay_reflex import replay
from game.sequencer import Sequencer
from game.state import DOWNED_BIT, JUGGLED_BIT, Tracker, build_state
from game.summarize import load_jsonl
from game.tactical import MIN_GAP, Tactical
from game.tests.test_pad import fake_pad
from game.tests.test_reflex import ATTACK, attack, exact
from game.tests.test_state import SID, idle

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "data" / "samples" / "practice_djin_vs_kaz.jsonl"
LATENCY = 2
OPTIONS = normalize_table(load_fallback()["kazuya"])
PUNISHERS, _ = load_punishers("kazuya")
PLAN_V = Draft202012Validator(json.loads((ROOT / "contracts" / "gameplan.schema.json").read_text()))
STATUS = 0x1942
BOT_Z = {"point_blank": -200.0, "close": 300.0, "mid": 1000.0, "far": 2000.0, "very_far": 3000.0}


def frames(bucket="close", start=0, n=60, human=None, bot=None):
    out = []
    for f in range(start, start + n):
        h = idle(0, f, **(human or {}))
        b = idle(1, f, position=(-6000.0, 1040.0, BOT_Z[bucket]), **(bot or {}))
        out.append((f, [h, b]))
    return out


class TRig:
    def __init__(self, difficulty=None, seed=0, human_slot=0, options=OPTIONS):
        self.pad, self.device = fake_pad()
        self.difficulty = difficulty or exact()
        self.rng = random.Random(seed)
        self.seq = Sequencer(self.pad, LATENCY, self.difficulty, self.rng)
        self.reflex = Reflex(self.seq, self.difficulty, LATENCY, PUNISHERS, self.rng)
        self.tactical = Tactical(self.seq, self.difficulty, LATENCY, options, self.rng)
        self.tracker = Tracker(SID)
        self.human_slot = human_slot
        self.records = []
        self.pressed = {}
        self.states = {}
        self.submitted = []
        submit = self.seq.submit

        def tracked(*args, **kwargs):
            move = submit(*args, **kwargs)
            self.submitted.append(move)
            return move

        self.seq.submit = tracked

    def step(self, f, pair, patch=None):
        state = build_state(pair, self.human_slot, f, SID)
        evs = self.tracker.step(state)
        if patch:
            patch(state)
        recs = self.reflex.step(state, evs)
        recs += self.tactical.step(state, evs, self.reflex)
        self.seq.on_frame(f, state["players"][1 - self.human_slot], self.reflex.live(state))
        self.pressed[f] = set(self.device.pressed)
        self.states[f] = state
        self.records.extend(recs)
        return recs

    def run(self, seq, patch=None):
        for f, pair in seq:
            self.step(f, pair, patch)
        return self

    def decisions(self):
        return [r for r in self.records if r.get("t") == "tactical" and r["source"] != "reflex"]

    def reflex_kinds(self):
        return [r["reflex"]["kind"] for r in self.records if r.get("source") == "reflex"]


def plus_five(state):
    state["derived"]["situation"] = "defense"
    state["derived"]["frame_advantage"] = -5


class DecisionTest(unittest.TestCase):
    def test_record_shape_and_plan(self):
        rig = TRig().run(frames("close"))
        plan = rig.records[0]
        self.assertEqual(plan["t"], "plan")
        self.assertEqual((plan["round"], plan["frame"], plan["session_id"]), (1, 0, SID))
        body = {k: v for k, v in plan.items() if k not in ("t", "round", "frame", "session_id")}
        self.assertEqual(list(PLAN_V.iter_errors(body)), [])
        recs = rig.decisions()
        self.assertGreaterEqual(len(recs), 3)
        self.assertEqual(recs[0]["frame"], 0)
        for rec in recs:
            self.assertEqual(rec["options"], list(CLASSES))
            self.assertIn(rec["chosen"], CLASSES)
            self.assertEqual(set(rec["probabilities"]), set(CLASSES))
            self.assertAlmostEqual(sum(rec["probabilities"].values()), 1.0, places=3)
            self.assertEqual(rec["source"], "default")
            self.assertEqual(rec["frame_asked"], rec["frame"])
            self.assertEqual(rec["session_id"], SID)
            self.assertEqual(rec["tactical"]["distance_bucket"], "close")
            self.assertEqual(rec["tactical"]["situation"], "neutral")
            self.assertIsInstance(rec["tactical"]["move"], str)
        gaps = [b["frame"] - a["frame"] for a, b in zip(recs, recs[1:])]
        self.assertTrue(all(g >= MIN_GAP for g in gaps), gaps)
        self.assertTrue(all(m.tag.get("tactical") in CLASSES for m in rig.submitted))
        self.assertTrue(any(p for p in rig.pressed.values()))

    def test_no_decision_when_not_actionable(self):
        busy = {"move_id": ATTACK, "frame_in_move": 5, "move_total": 41, "free_movement": 0}
        rig = TRig().run(frames("close", bot=busy))
        self.assertEqual(rig.decisions(), [])
        self.assertEqual(rig.submitted, [])

    def test_prepress_just_before_actionable(self):
        near = {"move_id": ATTACK, "frame_in_move": 38, "move_total": 41, "free_movement": 0}
        rig = TRig().run(frames("close", n=10, bot=near))
        recs = rig.decisions()
        self.assertEqual(len(recs), 1)
        self.assertTrue(recs[0]["tactical"]["prepress"])
        self.assertTrue(rig.submitted[0].prepress)
        self.assertIsNone(rig.submitted[0].start_frame)
        rig.run(frames("close", start=10, n=5))
        self.assertEqual(rig.submitted[0].start_frame, 10)

    def test_no_decision_while_reflex_pending(self):
        rig = TRig()
        rig.reflex.pending_guard = ("b", 10 ** 9)
        rig.run(frames("close", n=30))
        self.assertEqual(rig.decisions(), [])

    def test_no_decision_in_combo_or_downed(self):
        rig = TRig().run(frames("close", n=30, human={"status": STATUS | JUGGLED_BIT, "free_movement": 0}))
        self.assertEqual(rig.decisions(), [])
        rig = TRig().run(frames("close", n=30, bot={"status": STATUS | DOWNED_BIT, "free_movement": 0}))
        self.assertEqual(rig.decisions(), [])

    def test_round_over_stops_decisions(self):
        rig = TRig().run(frames("close", n=30, human={"health": 0}))
        self.assertEqual(rig.decisions(), [])
        self.assertTrue(all(p == set() for p in rig.pressed.values()))

    def test_oki_when_human_is_down(self):
        rig = TRig().run(frames("close", n=40, human={"status": STATUS | DOWNED_BIT, "free_movement": 0}))
        recs = rig.decisions()
        self.assertGreaterEqual(len(recs), 1)
        for rec in recs:
            self.assertEqual(rec["tactical"]["situation"], "knockdown")
            self.assertEqual(rec["probabilities"]["launcher"], 0.0)
            self.assertEqual(rec["probabilities"]["sidestep"], 0.0)


class WeightTest(unittest.TestCase):
    def first(self, bucket, difficulty=None, patch=None, seed=0):
        rig = TRig(difficulty, seed=seed).run(frames(bucket, n=1), patch)
        return rig.decisions()[0]

    def test_far_prefers_approach_and_temperature_flattens(self):
        sharp = self.first("very_far", exact())["probabilities"]
        flat = self.first("very_far", Difficulty.preset(1))["probabilities"]
        self.assertGreater(sharp["approach"], 0.6)
        self.assertGreater(flat["approach"], 0.3)
        self.assertLess(flat["approach"], sharp["approach"])
        self.assertLess(sharp["mid"], 0.01)

    def test_close_prefers_attacks(self):
        probs = self.first("close")["probabilities"]
        attacks = probs["mid"] + probs["low"] + probs["throw"] + probs["launcher"]
        self.assertGreater(attacks, 0.7)
        self.assertLess(probs["approach"], 0.05)

    def test_plus_frames_rules(self):
        neutral = self.first("close")["probabilities"]
        plus = self.first("close", patch=plus_five)
        self.assertEqual(plus["tactical"]["situation"], "defense")
        self.assertEqual(plus["probabilities"]["approach"], 0.0)
        self.assertGreater(plus["probabilities"]["throw"], neutral["throw"])
        self.assertLess(plus["probabilities"]["backdash"], neutral["backdash"])

    def test_movement_gating(self):
        rookie = Difficulty.preset(1)
        for seed in range(40):
            for rec in TRig(rookie, seed=seed).run(frames("close", n=40)).decisions():
                self.assertEqual(rec["probabilities"]["sidestep"], 0.0)
                self.assertNotEqual(rec["chosen"], "sidestep")
                self.assertNotIn("f,n,d", rec["tactical"]["move"])
        moves = set()
        steps = 0
        for seed in range(40):
            rig = TRig(Difficulty.preset(3), seed=seed).run(frames("very_far", n=40))
            for rec in rig.decisions():
                moves.add(rec["tactical"]["move"])
                steps += rec["probabilities"]["sidestep"] > 0
        self.assertIn("f,n,d,df,f,n,d,df", moves)
        self.assertGreater(steps, 0)

    def test_sidestep_direction_follows_side(self):
        seen = {}
        for seed in range(60):
            for rec in TRig(exact(), seed=seed).run(frames("mid", n=20)).decisions():
                if rec["chosen"] == "sidestep":
                    seen[rec["tactical"]["move"]] = rec["tactical"]["direction"]
        self.assertEqual(seen, {"u": "right", "d": "left"})


class ThreatTest(unittest.TestCase):
    def test_threat_aborts_active_movement(self):
        rig = TRig(exact(0))
        rig.seq.submit("F", tactical="approach")
        rig.run(attack(0, "mid", start=100, length=20))
        self.assertIn("tactical_abort", rig.reflex_kinds())
        aborted = rig.submitted[0]
        self.assertTrue(aborted.cancelled)
        self.assertEqual(aborted.done_frame, 100)
        self.assertEqual(rig.pressed[99], {"DPAD_LEFT"})
        self.assertEqual(rig.pressed[100], {"DPAD_RIGHT"})
        self.assertEqual(rig.pressed[101], {"DPAD_RIGHT"})
        self.assertIn("block", rig.reflex_kinds())

    def test_queued_tactical_discarded_on_threat(self):
        rig = TRig(exact(0))
        queued = rig.seq.submit("df+1", earliest=10 ** 6, tactical="mid")
        rig.run(attack(0, "low", start=100, length=20))
        self.assertIn("tactical_cancel", rig.reflex_kinds())
        self.assertTrue(queued.cancelled)
        self.assertEqual(rig.pressed[101], {"DPAD_DOWN", "DPAD_RIGHT"})

    def test_active_attack_is_not_aborted(self):
        rig = TRig(exact(0))
        rig.seq.submit("df+1", tactical="mid")
        rig.run(attack(0, "mid", start=100, length=20, lead=1))
        self.assertNotIn("tactical_abort", rig.reflex_kinds())


class ReplayTest(unittest.TestCase):
    def test_sample_dry_run_is_deterministic(self):
        states = [r for r in load_jsonl(SAMPLE) if r.get("t") == "state"]
        first = replay(states, Difficulty.preset(3), seed=1, tactical=True, options=OPTIONS)
        second = replay(states, Difficulty.preset(3), seed=1, tactical=True, options=OPTIONS)
        self.assertEqual(first[0], second[0])
        decisions = [r for r in first[0] if r.get("t") == "tactical" and r["source"] != "reflex"]
        self.assertGreater(len(decisions), 10)
        self.assertTrue(all(r["chosen"] in CLASSES for r in decisions))
        self.assertEqual({r["source"] for r in decisions}, {"default"})
        self.assertEqual([r["t"] for r in first[0]].count("plan"), 1)
        chosen = {r["chosen"] for r in decisions}
        self.assertTrue(chosen & set(MOVEMENT_CLASSES))
        self.assertTrue(chosen - set(MOVEMENT_CLASSES))


if __name__ == "__main__":
    unittest.main()
