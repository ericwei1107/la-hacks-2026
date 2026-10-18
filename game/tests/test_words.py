import unittest
from pathlib import Path

from game.state import DOWNED_BIT, JUGGLED_BIT, build_state
from game.summarize import load_jsonl
from game.tests.test_state import SID, idle
from game.words import (frame_words, health_words, lead_words, recent_words, stance_words, state_sentence, timer_words)

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"
STRIDE = 50


def state(frame=100, human=None, bot=None, human_slot=0):
    pair = [idle(0, frame, **(human or {})), idle(1, frame, **(bot or {}))]
    return build_state(pair, human_slot, frame, SID)


def decision(frame, action, actor=0, round_=1):
    return {"t": "event", "session_id": SID, "frame": frame, "round": round_, "kind": "decision_point", "actor": actor,
            "situation": "after_block:df1", "action": action}


class BucketTest(unittest.TestCase):
    def test_frame_words(self):
        self.assertEqual([frame_words(v) for v in (-12, -10, -5, -1, 0, 1, 9, 10, 25)],
                         ["a big disadvantage", "a big disadvantage", "a small disadvantage", "a small disadvantage", "even frames",
                          "a small advantage", "a small advantage", "a big advantage", "a big advantage"])
        self.assertIsNone(frame_words(None))

    def test_lead_and_health(self):
        full = {"health": 190, "max_health": 190}

        def hp(h):
            return {"health": h, "max_health": 190}

        self.assertEqual(lead_words(full, hp(100)), "far ahead")
        self.assertEqual(lead_words(full, hp(160)), "ahead")
        self.assertEqual(lead_words(full, hp(180)), "even")
        self.assertEqual(lead_words(hp(160), full), "behind")
        self.assertEqual(lead_words(hp(100), full), "far behind")
        self.assertEqual([health_words(hp(h)) for h in (190, 95, 90, 38, 30)], ["healthy", "healthy", "low", "critical", "critical"])

    def test_stance(self):
        self.assertEqual(stance_words(state()["players"][0]), "standing")
        self.assertEqual(stance_words(state(human={"status": 0x3929, "basic_state": 7})["players"][0]), "crouching")
        self.assertEqual(stance_words(state(human={"status": 0x1052, "basic_state": 2})["players"][0]), "blocking")
        self.assertEqual(stance_words(state(human={"status": 0x1942 | DOWNED_BIT})["players"][0]), "on the ground")
        self.assertEqual(stance_words(state(human={"status": 0x1942 | JUGGLED_BIT})["players"][0]), "being juggled")
        self.assertEqual(stance_words(state(human={"basic_state": 25})["players"][0]), "in the air")
        attacking = state(human={"hit_level": 0xA000050F, "hit_level_name": "high", "free_movement": 0})["players"][0]
        self.assertEqual(stance_words(attacking), "attacking")
        thrown = state(human={"being_thrown": 0xE000001F})["players"][0]
        self.assertEqual(stance_words(thrown), "being thrown")

    def test_timer(self):
        self.assertEqual([timer_words(t) for t in (59, 45.5, 30, 20.5, 10, 8, 2)],
                         ["early in the round", "early in the round", "midway through the round", "midway through the round",
                          "late in the round", "the final seconds of the round", "the final seconds of the round"])
        self.assertIsNone(timer_words(None))


class SentenceTest(unittest.TestCase):
    def test_deterministic_and_shape(self):
        s = state()
        first, second = state_sentence(s), state_sentence(s)
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("The opponent is standing"))
        self.assertTrue(first.endswith("The stage is open."))
        self.assertIn("The bot is even on health.", first)
        self.assertIn("early in the round", first)
        self.assertNotIn("heat active", first)
        self.assertIn("heat available", first)
        self.assertTrue(first.isascii())
        self.assertFalse(any(ch.isdigit() for ch in first))

    def test_frame_and_distance_sentence(self):
        s = state(bot={"position": (-6000.0, 1040.0, 400.0)})
        s["derived"]["frame_advantage"] = -6
        text = state_sentence(s)
        self.assertIn("The opponent is at a small disadvantage, standing at close range.", text)
        far = state(bot={"position": (-6000.0, 1040.0, 3000.0)})
        self.assertIn("standing far away", state_sentence(far))

    def test_health_and_flags(self):
        s = state(human={"health": 30, "heat_active": 1, "heat_used": 1}, bot={"health": 150, "rage_active": 1})
        text = state_sentence(s)
        self.assertIn("The opponent has critical health with heat active.", text)
        self.assertIn("The bot is healthy with heat available and rage active.", text)
        self.assertIn("The bot is far ahead on health.", text)

    def test_recent_action(self):
        s = state(frame=300)
        events = [decision(250, "block_low"), {"t": "event", "session_id": SID, "frame": 290, "round": 1, "kind": "whiff", "actor": 1}]
        self.assertIn("Recently the opponent crouch-blocked after blocking.", state_sentence(s, events))
        self.assertIsNone(recent_words([decision(100, "block_low")], 0, 300, 1))
        self.assertIsNone(recent_words([decision(290, "block_low", round_=2)], 0, 300, 1))
        self.assertIn("Recently the opponent whiffed a move.",
                      state_sentence(s, [{"t": "event", "session_id": SID, "frame": 290, "round": 1, "kind": "whiff", "actor": 0}]))
        self.assertNotIn("Recently", state_sentence(s, []))
        self.assertNotIn("Recently", state_sentence(s))

    def test_human_slot_one(self):
        s = state(human_slot=1, human={"health": 190}, bot={"health": 60})
        text = state_sentence(s)
        self.assertIn("The bot is healthy", text)
        self.assertIn("The opponent has low health", text)


class SampleTest(unittest.TestCase):
    def check(self, path):
        states = [r for r in load_jsonl(path) if r.get("t") == "state"]
        self.assertGreater(len(states), 0)
        for s in states[::STRIDE]:
            text = state_sentence(s)
            self.assertTrue(text and text.isascii(), text)
            self.assertFalse(any(ch.isdigit() for ch in text), text)
            self.assertTrue(text.endswith("The stage is open."), text)
            self.assertLess(len(text), 450, text)
            self.assertEqual(text, state_sentence(s))

    def test_practice_sample(self):
        self.check(SAMPLES / "practice_djin_vs_kaz.jsonl")

    def test_versus_sample(self):
        self.check(SAMPLES / "versus_djin_vs_kaz_l3.zip")


if __name__ == "__main__":
    unittest.main()
