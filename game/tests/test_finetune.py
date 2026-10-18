import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from game.finetune import (OPTIONS, QUESTIONS, TRAIN_META, assign_splits, balanced_train, build, drop_recent, export, label_counts,
                           labels, main, majority_baseline, majority_labels, minority_count, pair, pick_action, run_eval, score,
                           sentences, session_points, shift_distance, shift_health, split, split_prompt, train_laya, variants,
                           yes_no_rows)
from game.laya import FakeAgent, Laya

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


class FakeModel:
    def __init__(self):
        self.epoch = -1
        self.mode = "eval"

    def to(self, device):
        return self

    def train(self):
        self.mode = "train"
        return self


class FakeTrainer:
    class TrainConfig:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def __init__(self, quality=(0.5, 1.0, 0.0)):
        self.quality = quality
        self.saved = []

    def resolve_device(self, device):
        return "cpu"

    def load_checkpoint(self, path):
        return FakeModel(), object(), {"max_len": 64, "head_max_len": 32, "temperature_by_options": {"noul:2": 1.0}}

    def items_from_rows(self, tok, rows, max_len, head_max_len):
        return [{"state": r["state"], "q": q, "target": [0.0, 1.0] if v else [1.0, 0.0]}
                for r in rows for q, v in r["expected"].items()], {}

    def train_model(self, model, tok, items, config, device, max_len, head_max_len, on_epoch_end=None):
        self.config = config
        for epoch in range(config.epochs):
            model.epoch = epoch
            on_epoch_end(epoch, 1.0 / (epoch + 1))

    def calibration_records(self, model, tok, items, device, max_len, head_max_len, batch_size=16):
        q = self.quality[min(model.epoch, len(self.quality) - 1)]
        out = []
        for it in items:
            truth = it["target"][1]
            p = 0.5 if q == 0.5 else (truth if q == 1.0 else 1.0 - truth)
            out.append((2, [0.0, 0.0] if p == 0.5 else ([0.0, 9.0] if p else [9.0, 0.0]), it["target"], 2))
        return out

    def save_checkpoint(self, model, tok, cfg, path):
        Path(path).mkdir(parents=True, exist_ok=True)
        (Path(path) / "model.safetensors").write_text(str(model.epoch), encoding="utf-8")
        (Path(path) / "rl_agent_config.json").write_text(json.dumps(cfg), encoding="utf-8")
        self.saved.append(model.epoch)


def split_lines():
    rows = []
    for k, text in enumerate(texts(24)):
        situation, action = (("sidestep_dir", ("none", "right")[k // 2 % 2]) if k % 2 else
                             ("after_block:df1", ("press", "block_high", "ss_right")[k % 3]))
        rows.append(pair(text, {"situation": situation, "action": action}))
    rows.append(pair(texts(25)[24], {"situation": "throw_break", "action": "break_1"}))
    return rows


def write_lines(path, lines):
    Path(path).write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    return path


class TrainEvalTest(unittest.TestCase):
    def test_pick_action_inverts_the_yes_no_labels(self):
        prior = {"after_block": Counter({"press": 5, "throw": 1, "ss_right": 3, "ss_left": 1}), "sidestep_dir": Counter({"none": 9, "right": 2}),
                 "low_defense": Counter({"hit": 9, "blocked": 1}), "throw_break": Counter({"none": 4, "break_1": 2})}
        yes = {"p": 0.95}
        no = {"p": 0.05}
        self.assertEqual(pick_action("after_block", {"opp_presses": yes, "opp_ducks": no, "opp_steps": no, "opp_passive": no}, prior), "press")
        self.assertEqual(pick_action("after_block", {"opp_presses": no, "opp_ducks": no, "opp_steps": yes, "opp_passive": no}, prior), "ss_right")
        self.assertEqual(pick_action("sidestep_dir", {"opp_steps": yes}, prior), "right")
        self.assertEqual(pick_action("sidestep_dir", {"opp_steps": no}, prior), "none")
        self.assertEqual(pick_action("low_defense", {"opp_ducks": yes}, prior), "blocked")
        self.assertEqual(pick_action("throw_break", {}, prior), "none")
        self.assertEqual(pick_action("sidestep_dir", {"opp_steps": yes}, {"sidestep_dir": Counter({"left": 3, "right": 1})}), "left")
        self.assertEqual(split_prompt(split_lines()[0]["prompt"])[1], "after_block")
        rows = yes_no_rows(split_lines())
        self.assertEqual(len(rows), 24)
        self.assertEqual(set(rows[0]["questions"]), set(QUESTIONS))
        self.assertEqual(rows[1]["expected"], {"opp_steps": False})

    def test_train_keeps_the_epoch_with_the_best_val_balanced_accuracy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            base = tmp / "base"
            base.mkdir()
            lines = split_lines()
            train = write_lines(tmp / "train.jsonl", lines)
            val = write_lines(tmp / "val.jsonl", lines[:12])
            trainer = FakeTrainer()
            logs = []
            meta = train_laya(train, val, tmp / "laya-ft", str(base), epochs=3, batch=32, micro=8, device="cpu", trainer=trainer,
                              log=lambda m, **_: logs.append(m))
            self.assertEqual([r["epoch"] for r in meta["epochs"]], [1, 2, 3])
            self.assertEqual(meta["best_epoch"], 2)
            self.assertEqual(meta["best"]["val_balanced"], 1.0)
            self.assertLess(meta["epochs"][2]["val_balanced"], 1.0)
            self.assertEqual((tmp / "laya-ft" / "model.safetensors").read_text(encoding="utf-8"), "1")
            self.assertFalse((tmp / "laya-ft.tmp").exists())
            self.assertEqual((trainer.config.micro_batch, trainer.config.grad_accum), (8, 4))
            self.assertEqual(json.loads((tmp / "laya-ft" / TRAIN_META).read_text(encoding="utf-8"))["best_epoch"], 2)
            self.assertEqual(sum("val balanced" in m for m in logs), 3)

    def test_eval_scores_base_and_finetuned_and_writes_the_eval_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            lines = split_lines()
            write_lines(tmp / "train.jsonl", lines)
            write_lines(tmp / "test.jsonl", lines)
            truth = {split_prompt(x["prompt"])[0]: (split_prompt(x["prompt"])[1], x["label"]) for x in lines}

            def oracle(text, key):
                fam, label = truth[text]
                want = labels(f"{fam}:any" if fam == "after_block" else fam, label)
                return 0.5 if key not in want else float(want[key])

            ft_dir = tmp / "laya-ft"
            ft_dir.mkdir()
            (ft_dir / TRAIN_META).write_text(json.dumps({"trained_at": "2026-10-18T11:00:00Z"}), encoding="utf-8")
            out = tmp / "eval" / "s.json"
            record = run_eval(tmp, Laya(agent=FakeAgent(answer=0.5)), Laya(agent=FakeAgent(answer=oracle)),
                              {"base": "base", "finetuned": str(ft_dir)}, out, "s", log=lambda *_, **__: None)
            saved = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(saved, record)
            for key in ("before", "after", "session_id", "model", "base", "finetuned", "baseline", "per_situation", "train_lines",
                        "test_lines", "trained_at"):
                self.assertIn(key, saved)
            self.assertEqual(saved["model"], "laya")
            self.assertEqual(saved["trained_at"], "2026-10-18T11:00:00Z")
            self.assertTrue(0 <= saved["before"] <= 1 and 0 <= saved["after"] <= 1)
            self.assertEqual(saved["finetuned"]["accuracy"], 1.0)
            self.assertEqual(saved["per_situation"]["sidestep_dir"]["finetuned"]["balanced_accuracy"], 1.0)
            self.assertEqual(saved["per_situation"]["throw_break"]["n"], 1)
            self.assertEqual(saved["base"]["accuracy"], saved["baseline"]["accuracy"])
            self.assertEqual(saved["test_lines"], len(lines))

    def test_startup_prefers_the_finetuned_weights(self):
        from unittest import mock
        from game import laya as laya_mod
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict("os.environ", {"DATA_DIR": tmp}):
            self.assertEqual(laya_mod.resolve_model(), (laya_mod.MODEL, "base"))
            ft = Path(tmp) / "models" / "laya-ft"
            ft.mkdir(parents=True)
            (ft / "model.safetensors").write_text("x")
            (ft / "rl_agent_config.json").write_text("{}")
            self.assertEqual(laya_mod.resolve_model(), (str(ft), "fine-tuned"))
            logs = []
            got = laya_mod.startup(log=lambda m, **_: logs.append(m), rounds=5, factory=lambda model: Laya(model, agent=FakeAgent(answer=0.5)))
            self.assertIsNotNone(got)
            self.assertIn("fine-tuned", logs[0])
            self.assertIn("p50", logs[1])
            self.assertIn("p95", logs[1])

            def broken(model):
                raise SystemExit("laya missing")

            logs.clear()
            self.assertIsNone(laya_mod.startup(log=lambda m, **_: logs.append(m), factory=broken))
            self.assertIn("plays without it", logs[-1])


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
