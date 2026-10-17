import random
import unittest

from game.difficulty import Difficulty
from game.reflex import Reflex, WAKEUP_LOGITS, load_punishers, load_wakeups, softmax, wakeup_situation
from game.sequencer import Sequencer
from game.state import Tracker, build_state
from game.tests.test_pad import fake_pad
from game.tests.test_reflex import FixedDelay as BaseFixedDelay
from game.tests.test_state import SID, idle

LATENCY = 2
WAKEUPS, _ = load_wakeups("kazuya")
PUNISHERS, _ = load_punishers("kazuya")
LYING = {"status": 0x6084, "move_id": 0x8007, "move_total": 60, "free_movement": 0, "basic_state": 12}
LANDING = {"status": 0x6084, "move_id": 0x8006, "move_total": 1, "free_movement": 0, "basic_state": 12}


class FixedDelay(BaseFixedDelay):
    mixup_temperature = 0.5


def exact(temperature=0.5):
    return Difficulty.preset(5).with_knobs(frame_perfect_chance=0.0, execution_error=0.0, mixup_temperature=temperature)


def frame_pair(f, bot=None, opp=None, distance=2000):
    a, b = idle(0, f, position=(-6000.0, 1040.0, -distance / 2)), idle(1, f, position=(-6000.0, 1040.0, distance / 2))
    a.update(opp or {})
    b.update(bot or {})
    return [a, b]


class Rig:
    def __init__(self, difficulty, seed=0):
        self.pad, self.device = fake_pad()
        self.rng = random.Random(seed)
        self.seq = Sequencer(self.pad, LATENCY, difficulty, self.rng)
        self.reflex = Reflex(self.seq, difficulty, LATENCY, PUNISHERS, self.rng, WAKEUPS)
        self.tracker = Tracker(SID)
        self.records = []
        self.pressed = {}

    def run(self, frames):
        for f, pair, distance in frames:
            state = build_state(pair, 0, f, SID)
            evs = self.tracker.step(state)
            self.records += self.reflex.step(state, evs)
            self.seq.on_frame(f, state["players"][1], self.reflex.live(state))
            self.pressed[f] = set(self.device.pressed)
        return self

    def wakeups(self):
        return [r for r in self.records if r["reflex"]["kind"] == "wakeup"]


def knockdown(start=100, landing=20, lying=80, distance=3000, opp=None):
    out = []
    for f in range(start - 2, start + landing + lying):
        bot = None
        if start <= f < start + landing:
            bot = dict(LANDING, frame_in_move=f - start + 1)
        elif f >= start + landing:
            bot = dict(LYING, frame_in_move=f - start - landing + 1)
        out.append((f, frame_pair(f, bot, opp, distance), distance))
    return out


class WakeupTimingTest(unittest.TestCase):
    def test_waits_for_lying_loop_then_reaction(self):
        rig = Rig(FixedDelay(10)).run(knockdown())
        recs = rig.wakeups()
        self.assertEqual(len(recs), 1)
        rec = recs[0]
        self.assertEqual(rec["frame_asked"], 121)
        self.assertEqual(rec["frame"], 121 + 10 - LATENCY)
        for f in range(98, rec["frame"]):
            self.assertEqual(rig.pressed[f], set(), f"frame {f}")
        self.assertNotEqual(rig.pressed[rec["frame"]], set())

    def test_once_per_knockdown(self):
        rig = Rig(FixedDelay(0)).run(knockdown(lying=200))
        self.assertEqual(len(rig.wakeups()), 1)

    def test_hit_off_the_ground_rearms(self):
        frames = knockdown(lying=120)
        for f, pair, _ in frames:
            if 125 <= f < 135:
                pair[1].update(move_id=0x1A6, move_total=40, status=0x7406, basic_state=14)
        rig = Rig(FixedDelay(20)).run(frames)
        recs = rig.wakeups()
        self.assertEqual(len(recs), 1)
        self.assertGreaterEqual(recs[0]["frame_asked"], 136)

    def test_face_down_uses_face_down_table(self):
        frames = knockdown()
        for _, pair, _ in frames:
            if pair[1]["move_id"] == 0x8007:
                pair[1].update(move_id=0x800A, basic_state=13)
        rec = Rig(FixedDelay(0)).run(frames).wakeups()[0]
        self.assertEqual(rec["reflex"]["face"], "face_down")
        self.assertTrue(rec["reflex"]["verified"])
        self.assertEqual(rec["options"], [o["notation"] for o in WAKEUPS["face_down"]])
        self.assertNotIn("3+4", rec["options"])

    def test_unknown_face_falls_back_unverified(self):
        frames = knockdown()
        for _, pair, _ in frames:
            if pair[1]["move_id"] == 0x8007:
                pair[1].update(basic_state=99)
        rec = Rig(FixedDelay(0)).run(frames).wakeups()[0]
        self.assertEqual(rec["options"], [o["notation"] for o in WAKEUPS["face_up"]])
        self.assertEqual(rec["reflex"]["face"], "basic_99")
        self.assertFalse(rec["reflex"]["verified"])

    def test_record_shape(self):
        rec = Rig(FixedDelay(0)).run(knockdown()).wakeups()[0]
        self.assertEqual(rec["source"], "reflex")
        self.assertIn(rec["chosen"], rec["options"])
        self.assertAlmostEqual(sum(rec["probabilities"].values()), 1.0, places=3)
        self.assertEqual(set(rec["probabilities"]), set(rec["options"]))


class WakeupChoiceTest(unittest.TestCase):
    def situation_of(self, distance, opp):
        state = build_state(frame_pair(200, LYING, opp, distance), 0, 200, SID)
        Tracker(SID).step(state)
        return wakeup_situation(state, state["players"][1], state["players"][0])

    def test_situations(self):
        recovering = {"move_id": 0x6A4, "frame_in_move": 20, "move_total": 41, "free_movement": 0, "first_active": 15,
                      "last_active": 15, "hit_level": 0x8000020A, "hit_level_name": "mid"}
        self.assertEqual(self.situation_of(3000, None), "far")
        self.assertEqual(self.situation_of(1000, None), "pressure")
        self.assertEqual(self.situation_of(1000, recovering), "recovering_close")
        self.assertEqual(self.situation_of(2000, recovering), "recovering_mid")
        attacking = dict(recovering, frame_in_move=15)
        self.assertEqual(self.situation_of(1000, attacking), "pressure")

    def test_favourite_per_situation_at_low_temperature(self):
        kinds = {o["notation"]: o["kind"] for o in WAKEUPS["face_up"]}
        expect = {"far": "stand", "recovering_close": "rising_mid", "recovering_mid": "spring_kick", "pressure": "back_roll"}
        for situation, kind in expect.items():
            probs = softmax({n: WAKEUP_LOGITS[situation][k] for n, k in kinds.items()}, 0.5)
            self.assertEqual(kinds[max(probs, key=probs.get)], kind, situation)

    def test_temperature_flattens(self):
        logits = {"a": 2.0, "b": 0.0}
        self.assertGreater(softmax(logits, 0.5)["a"], softmax(logits, 2.0)["a"])

    def test_far_wakeup_mostly_stands_at_level_5(self):
        chosen = [Rig(exact(0.5), seed=s).run(knockdown(distance=3000)).wakeups()[0]["chosen"] for s in range(60)]
        self.assertGreater(chosen.count("u") / len(chosen), 0.8)

    def test_pressure_wakeup_rolls(self):
        chosen = [Rig(exact(0.5), seed=s).run(knockdown(distance=1000)).wakeups()[0]["chosen"] for s in range(60)]
        self.assertGreater(sum(1 for c in chosen if c in ("b", "1")) / len(chosen), 0.8)


if __name__ == "__main__":
    unittest.main()
