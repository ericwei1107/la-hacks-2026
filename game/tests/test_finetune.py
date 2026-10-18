import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from game.finetune import QUESTIONS, build, labels, majority_baseline, split

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"
NEUTRAL = SAMPLES / "versus_djin_vs_kaz_l3_neutral.zip"


class LabelTest(unittest.TestCase):
    def test_after_block_actions_answer_every_question(self):
        for action in ("press", "throw", "duck", "block_low", "block_high", "none", "backdash", "ss_left", "ss_right"):
            got = labels("after_block:df1", action)
            self.assertEqual(set(got), set(QUESTIONS), action)
        self.assertTrue(labels("after_block:df1", "press")["opp_presses"])
        self.assertFalse(labels("after_block:df1", "press")["opp_passive"])
        self.assertTrue(labels("after_block:b4", "duck")["opp_ducks"])
        self.assertTrue(labels("after_block:b4", "ss_right")["opp_steps"])
        self.assertTrue(labels("after_block:b4", "block_high")["opp_passive"])

    def test_other_situations(self):
        self.assertEqual(labels("low_defense", "hit"), {"opp_ducks": False})
        self.assertEqual(labels("low_defense", "blocked"), {"opp_ducks": True})
        self.assertEqual(labels("sidestep_dir", "left"), {"opp_steps": True})
        self.assertEqual(labels("sidestep_dir", "none"), {"opp_steps": False})
        self.assertEqual(labels("throw_break", "break_2"), {})
        self.assertEqual(labels("after_block:df1", "unknown"), {})


class BuildTest(unittest.TestCase):
    def test_samples_build_with_one_session_held_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "set.jsonl"
            rows, skipped, chosen, path = build([str(SAMPLES)], None, out)
            self.assertEqual(path, out)
            self.assertTrue(rows)
            lines = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(lines), len(rows))
            for row in lines:
                self.assertTrue(row["text"])
                self.assertTrue(row["questions"])
                self.assertTrue(set(row["questions"]) <= set(QUESTIONS))
                self.assertIn(row["split"], ("train", "heldout"))
                self.assertIn(row["action"], (row["action"],))
            sessions = {r["session_id"] for r in rows}
            self.assertGreaterEqual(len(sessions), 2)
            held = {r["session_id"] for r in rows if r["split"] == "heldout"}
            self.assertEqual(held, {chosen})
            self.assertEqual(chosen, max(sessions))
            neutral = [r for r in rows if r["source"] == NEUTRAL.name]
            counts = Counter((r["situation"], r["action"]) for r in neutral)
            self.assertEqual(counts[("low_defense", "hit")], 13)
            self.assertEqual(sum(1 for (s, a), n in skipped.items() if s == "throw_break"), len([k for k in skipped if k[0] == "throw_break"]))
            self.assertTrue(all(s == "throw_break" for s, _ in skipped))

    def test_explicit_heldout_and_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows, _, chosen, _ = build([str(NEUTRAL), str(SAMPLES / "versus_djin_vs_kaz_l3.zip")], "neutral", Path(tmp) / "x.jsonl")
            self.assertEqual({r["source"] for r in rows if r["split"] == "heldout"}, {NEUTRAL.name})
            self.assertEqual({r["session_id"] for r in rows if r["split"] == "heldout"}, {chosen})
            with self.assertRaises(SystemExit):
                split(rows, "no-such-session")
            base = majority_baseline(rows)
            self.assertEqual(set(base), set(QUESTIONS))
            for row in base.values():
                self.assertTrue(row["accuracy"] is None or 0 <= row["accuracy"] <= 1)
            self.assertIsNotNone(base["opp_ducks"]["accuracy"])


if __name__ == "__main__":
    unittest.main()
