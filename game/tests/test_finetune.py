import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from game.finetune import (OPTIONS, QUESTIONS, assign_splits, balanced_train, build, drop_recent, export, label_counts, labels,
                           main, majority_baseline, majority_labels, minority_count, pair, score, sentences, session_points,
                           shift_distance, shift_health, split, variants)

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"
NEUTRAL = SAMPLES / "versus_djin_vs_kaz_l3_neutral.zip"
TEXT = ("Recently the opponent had a move blocked. The opponent is at a small disadvantage, standing at close range. "
        "The opponent is healthy with heat available. The bot is healthy with heat available. The bot is even on health. "
        "It is early in the round. The stage is open.")


def point(sid, round_, frame, situation, action, text=TEXT):
    return {"t": "event", "session_id": sid, "frame": frame, "round": round_, "kind": "decision_point", "actor": 0, "target": 1,
            "situation": situation, "action": action, "detail": {"start_frame": frame - 5, "state_text": text}}


def recording(path, sid, events):
    lines = [{"t": "state", "session_id": sid, "frame": 0, "round": 1, "human_slot": 0}] + events
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return path


def read_lines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


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


class AugmentTest(unittest.TestCase):
    def test_four_distinct_variants_that_keep_the_situation(self):
        row = {"session_id": "s", "round": 1, "frame": 10, "situation": "low_defense", "action": "hit", "text": TEXT}
        got = variants(row)
        self.assertEqual(len(got), 4)
        self.assertEqual(len(set(got)), 4)
        self.assertNotIn(TEXT, got)
        for text in got:
            self.assertNotIn("far away", text)
            self.assertIn("The stage is open.", text)
        self.assertEqual(variants(row), got)

    def test_distance_shifts_stay_inside_the_situation(self):
        parts = sentences(TEXT)
        self.assertIn("standing touching the bot.", " ".join(shift_distance(parts, "throw_break", -1)))
        self.assertIsNone(shift_distance(parts, "throw_break", 1))
        self.assertIn("standing at mid range.", " ".join(shift_distance(parts, "after_block:df1", 1)))
        far = sentences(TEXT.replace("at close range", "far away"))
        self.assertIsNone(shift_distance(far, "low_defense", -1))
        self.assertIn("at mid range", " ".join(shift_distance(far, "sidestep_dir", -1)))

    def test_health_shifts_both_players_together(self):
        shifted = " ".join(shift_health(sentences(TEXT), 1))
        self.assertIn("The opponent has low health with heat available.", shifted)
        self.assertIn("The bot has low health with heat available.", shifted)
        self.assertIsNone(shift_health(sentences(TEXT), -1))
        mixed = TEXT.replace("The bot is healthy", "The bot has low health")
        self.assertIsNone(shift_health(sentences(mixed), 1))
        far = TEXT.replace("even on health", "far ahead on health")
        self.assertIsNone(shift_health(sentences(far), 1))

    def test_drop_recent_only_drops_the_recent_clause(self):
        self.assertEqual(" ".join(drop_recent(sentences(TEXT))), TEXT.split(". ", 1)[1])
        self.assertIsNone(drop_recent(sentences(TEXT.split(". ", 1)[1])))


def texts(n, distance="at close range"):
    out = []
    for i in range(n):
        lead = ("Recently the opponent had a move blocked. ", "Recently the opponent whiffed a move. ", "")[i % 3]
        when = ("early in the round", "midway through the round", "late in the round", "the final seconds of the round")[i // 3 % 4]
        frames = ("a small disadvantage", "a big disadvantage", "even frames", "a small advantage", "a big advantage")[i // 12 % 5]
        out.append(f"{lead}The opponent is at {frames}, standing {distance}. The opponent is healthy with heat available. "
                   f"The bot is healthy with heat available. The bot is even on health. It is {when}. The stage is open.")
    return out


def train_rows(situation, labels_and_counts):
    rows = []
    for label, n in labels_and_counts:
        for k, text in enumerate(texts(n)):
            rows.append({"session_id": "s", "round": 1, "frame": len(rows), "situation": situation, "action": label, "text": text})
    return rows


class RebalanceTest(unittest.TestCase):
    def test_minority_gets_up_to_8_and_majority_is_trimmed_to_65_percent(self):
        rows = train_rows("low_defense", [("hit", 40), ("blocked", 4)])
        lines = balanced_train(rows)
        counts = label_counts(lines)["low_defense"]
        self.assertEqual(counts["blocked"], 4 * 9)
        self.assertLessEqual(counts["hit"] / sum(counts.values()), 0.65)
        self.assertEqual(counts["hit"], 66)
        self.assertEqual(len({(x["prompt"], x["label"]) for x in lines}), len(lines))
        originals = {(pair(r["text"], r)["prompt"], r["action"]) for r in rows}
        self.assertTrue(originals <= {(x["prompt"], x["label"]) for x in lines})

    def test_balanced_situations_keep_four_variants(self):
        rows = train_rows("after_block:df1", [("press", 6), ("ss_right", 4), ("duck", 2)])
        counts = label_counts(balanced_train(rows))["after_block"]
        self.assertEqual(dict(counts), {"press": 30, "ss_right": 20, "duck": 10})
        self.assertEqual(minority_count(6, 6), 4)
        self.assertEqual(minority_count(10, 2), 8)

    def test_val_and_test_are_never_augmented(self):
        rows = train_rows("low_defense", [("hit", 20), ("blocked", 2)])
        for r in rows[:3]:
            r["split"] = "val"
        rows[3]["split"] = "test"
        for r in rows[4:]:
            r["split"] = "train"
        from game.finetune import export_lines
        lines = export_lines(rows)
        self.assertEqual(len(lines["val"]), 3)
        self.assertEqual(len(lines["test"]), 1)
        self.assertEqual(lines["val"], [pair(r["text"], r) for r in rows[:3]])
        self.assertEqual(lines["test"], [pair(rows[3]["text"], rows[3])])
        self.assertEqual(sum(label_counts(lines["train"])["low_defense"].values()), len(balanced_train(rows[4:])))


class BaselineTest(unittest.TestCase):
    def line(self, situation, label):
        return pair(TEXT, {"situation": situation, "action": label})

    def test_majority_accuracy_and_balanced_accuracy(self):
        train = [self.line("sidestep_dir", "none")] * 3 + [self.line("sidestep_dir", "left"),
                                                           self.line("low_defense", "hit"), self.line("low_defense", "hit")]
        majority = majority_labels(train)
        self.assertEqual(majority, {"sidestep_dir": "none", "low_defense": "hit"})
        test = ([self.line("sidestep_dir", "none")] * 3 + [self.line("sidestep_dir", "right")]
                + [self.line("low_defense", "hit"), self.line("low_defense", "blocked")])
        got = score(test, majority)
        self.assertAlmostEqual(got["sidestep_dir"]["accuracy"], 0.75)
        self.assertAlmostEqual(got["sidestep_dir"]["balanced"], 0.5)
        self.assertAlmostEqual(got["low_defense"]["accuracy"], 0.5)
        self.assertAlmostEqual(got["overall"]["accuracy"], 4 / 6)
        self.assertAlmostEqual(got["overall"]["balanced"], 0.5)
        self.assertEqual(got["overall"]["n"], 6)

    def test_cli_baseline_reads_the_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, part in (("train", [self.line("sidestep_dir", "none")] * 2),
                               ("val", [self.line("sidestep_dir", "left")]), ("test", [self.line("sidestep_dir", "none")])):
                (Path(tmp) / f"{name}.jsonl").write_text("".join(json.dumps(x) + "\n" for x in part), encoding="utf-8")
            self.assertEqual(main(["baseline", "--dir", tmp]), 0)


class ExportTest(unittest.TestCase):
    def make(self, tmp):
        tmp = Path(tmp)
        rec = tmp / "recordings"
        rec.mkdir()
        train_events = []
        for r in range(1, 11):
            train_events += [point("2026-10-18T05-00-00_a", r, 100 * r + k, "sidestep_dir", ("none", "left", "right")[k % 3])
                             for k in range(3)]
            train_events.append(point("2026-10-18T05-00-00_a", r, 100 * r + 50, "after_block:df1", "press"))
        recording(rec / "a.jsonl", "2026-10-18T05-00-00_a", train_events)
        recording(rec / "b.jsonl", "2026-10-18T07-30-06_b", [point("2026-10-18T07-30-06_b", 1, 10, "throw_break", "break_1"),
                                                              point("2026-10-18T07-30-06_b", 1, 20, "low_defense", "blocked")])
        recording(rec / "c.jsonl", "2026-10-18T05-00-00_a", [point("2026-10-18T05-00-00_a", 1, 5, "low_defense", "hit")])
        recording(rec / "d.jsonl", "2026-10-18T06-00-00_d", [point("2026-10-18T06-00-00_d", 1, 5, "low_defense", "hit", text=None),
                                                              point("2026-10-18T06-00-00_d", 1, 6, "wakeup", "none")])
        return rec, tmp / "out"

    def test_export_writes_three_splits_of_prompt_label_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec, out = self.make(tmp)
            rows, skipped, val, lines, paths = export([str(rec)], out, log=lambda *_: None)
            self.assertEqual(len(rows), 42)
            self.assertEqual(skipped[("low_defense", "no state_text")], 1)
            self.assertEqual(skipped[("wakeup", "none")], 1)
            got = {name: read_lines(out / f"{name}.jsonl") for name in ("train", "val", "test")}
            for part in got.values():
                for line in part:
                    self.assertEqual(set(line), {"prompt", "label"})
                    self.assertIn("Answer with exactly one option name", line["prompt"])
            self.assertEqual([x["label"] for x in got["test"]], ["break_1", "blocked"])
            self.assertIn("Options: break_1, break_2, break_12, none.", got["test"][0]["prompt"])
            train_rows = [r for r in rows if r["split"] == "train"]
            val_rows = [r for r in rows if r["split"] == "val"]
            self.assertEqual(len(got["train"]), 5 * len(train_rows))
            self.assertEqual(len(got["val"]), len(val_rows))
            self.assertEqual(len(val), 1)
            self.assertEqual(len(val_rows), 4)
            for line in got["train"]:
                fam = "after_block" if "Options: press" in line["prompt"] else "sidestep_dir"
                self.assertIn(line["label"], OPTIONS[fam])

    def test_val_is_whole_session_rounds_and_test_is_the_held_out_session(self):
        rows = [{"session_id": s, "round": r, "frame": f, "situation": "sidestep_dir", "action": "none", "text": TEXT}
                for s in ("x", "y", "2026-10-18T07-30-06_z") for r in range(1, 6) for f in range(4)]
        groups = assign_splits(rows, fraction=0.1)
        self.assertTrue(all(r["split"] == "test" for r in rows if r["session_id"].startswith("2026-10-18T07-30-06")))
        val = {(r["session_id"], r["round"]) for r in rows if r["split"] == "val"}
        train = {(r["session_id"], r["round"]) for r in rows if r["split"] == "train"}
        self.assertEqual(val, groups)
        self.assertFalse(val & train)
        self.assertEqual(sum(1 for r in rows if r["split"] == "val"), 4)
        with self.assertRaises(SystemExit):
            assign_splits([dict(r) for r in rows if r["session_id"] == "x"])

    def test_recording_without_recorded_points_is_replayed(self):
        sid, points, origin = session_points(SAMPLES / "versus_djin_vs_kaz_l3_neutral.zip")
        self.assertEqual(origin, "recorded")
        self.assertTrue(points)
        sid, points, origin = session_points(SAMPLES / "practice_djin_vs_kaz.jsonl")
        self.assertEqual(origin, "replayed")
        self.assertTrue(sid)

    def test_cli_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec, out = self.make(tmp)
            self.assertEqual(main(["export", str(rec), "--out-dir", str(out)]), 0)
            self.assertTrue((out / "train.jsonl").exists() and (out / "val.jsonl").exists() and (out / "test.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
