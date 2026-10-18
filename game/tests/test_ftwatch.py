import json
import os
import subprocess
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import torch

from game import finetune as ft
from game import ftwatch as fw
from game.tests.test_finetune import FakeTrainer, split_lines, texts
from game.state import build_state
from game.tests.test_state import SID, idle


class Encoder(torch.nn.Module):
    def __init__(self, n=10):
        super().__init__()
        self.layers = torch.nn.ModuleList(torch.nn.Linear(2, 2) for _ in range(n))
        self.norm = torch.nn.LayerNorm(2)


class TinyModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = Encoder()
        self.head = torch.nn.Linear(2, 2)
        self.epoch = 0


class CpuTrainer(FakeTrainer):
    def __init__(self, quality=(0.0, 1.0)):
        super().__init__(quality)
        self.loaded = []

    def load_checkpoint(self, path):
        self.loaded.append(path)
        self.model = TinyModel()
        return self.model, object(), {"max_len": 64, "head_max_len": 32, "temperature_by_options": {"noul:2": 1.0}}

    def train_model(self, model, tok, items, config, device, max_len, head_max_len, on_epoch_end=None):
        self.config = config
        self.items = items
        self.trainable = [n for n, p in model.named_parameters() if p.requires_grad]
        for epoch in range(config.epochs):
            model.epoch = epoch + 1
            on_epoch_end(epoch, 0.5)


def event(frame, round_, kind, **extra):
    return {"t": "event", "session_id": SID, "frame": frame, "round": round_, "kind": kind, **extra}


def decision(k, text):
    situation, action = (("sidestep_dir", ("none", "right")[k % 2]) if k % 3 else ("after_block:df1", ("press", "block_high")[k % 2]))
    return event(100 + k, 1, "decision_point", actor=0, target=1, situation=situation, action=action,
                 detail={"start_frame": 90 + k, "correct": True, "state_text": text})


def write_session(root, sid, points=12, ended=True, match_over=True, recording_name=None):
    rec = root / "recordings" / f"{recording_name or sid}.jsonl"
    rec.parent.mkdir(parents=True, exist_ok=True)
    lines = [build_state([idle(0, 0), idle(1, 0)], 0, 0, sid)]
    lines += [dict(decision(k, t), session_id=sid) for k, t in enumerate(texts(points))]
    lines.append(dict(event(4000, 1, "round_end", winner=0, detail={"match_over": match_over}), session_id=sid))
    rec.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    meta = {"session_id": sid, "started_at": "2026-10-18T12:00:00Z", "ended_at": "2026-10-18T12:05:00Z" if ended else None,
            "player": "sahil", "human_slot": 0, "human_character": "devil_jin", "bot_character": "kazuya", "difficulty": 3,
            "mode": "versus", "rounds": [{"round": 1, "winner": 0}], "recording": str(rec)}
    (root / "sessions").mkdir(parents=True, exist_ok=True)
    (root / "sessions" / f"{sid}.json").write_text(json.dumps(meta), encoding="utf-8")
    return rec


def seed_weights(root, version=None, train_meta=True):
    model = root / "models" / "laya-ft"
    model.mkdir(parents=True)
    (model / "model.safetensors").write_text("v0", encoding="utf-8")
    (model / "rl_agent_config.json").write_text("{}", encoding="utf-8")
    if train_meta:
        (model / ft.TRAIN_META).write_text(json.dumps({"trained_at": "2026-10-18T09:00:00Z"}), encoding="utf-8")
    if version is not None:
        (model / ft.MODEL_META).write_text(json.dumps({"version": version}), encoding="utf-8")
    return model


def seed_splits(root):
    folder = root / "finetune"
    folder.mkdir(parents=True, exist_ok=True)
    lines = split_lines()
    for name in ("train", "test"):
        (folder / f"{name}.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    return lines


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class WatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.logs = []
        self.trainer = CpuTrainer()
        self.clock = Clock()
        self.test_lines = seed_splits(self.root)

    def watcher(self, **kw):
        kw.setdefault("trainer", self.trainer)
        return fw.Watcher(self.root, device="cpu", precision=lambda dev: nullcontext(), clock=self.clock,
                          log=lambda m, **_: self.logs.append(m), **kw)

    def test_finished_match_is_exported_fine_tuned_evaluated_and_versioned(self):
        model = seed_weights(self.root, version=4)
        watcher = self.watcher()
        sid = "2026-10-18T12-00-00_sahil_djin_vs_kaz"
        write_session(self.root, sid)
        [(got_sid, meta)] = watcher.poll()
        self.assertEqual(got_sid, sid)
        inc = self.root / "finetune" / "incremental" / f"{sid}.jsonl"
        lines = ft.read_rows(inc)
        self.assertGreater(len(lines), 12)
        self.assertTrue(all(set(x) == {"prompt", "label"} for x in lines))
        rows, _ = ft.gather([self.root / "recordings" / f"{sid}.jsonl"], log=lambda *a: None)
        for r in rows:
            r["split"] = "train"
        self.assertEqual(lines, ft.balanced_train(rows))
        cfg = self.trainer.config
        self.assertEqual((cfg.epochs, cfg.micro_batch, cfg.grad_accum, cfg.encoder_lr, cfg.head_lr), (1, 16, 1, 2e-5, 2e-5))
        self.assertEqual(self.trainer.loaded, [str(model)])
        layers = {n.split(".")[2] for n in self.trainer.trainable if n.startswith("encoder.layers.")}
        self.assertEqual(layers, {str(i) for i in range(2, 10)})
        self.assertIn("head.weight", self.trainer.trainable)
        self.assertEqual(meta["test"]["before"]["accuracy"] < meta["test"]["after"]["accuracy"], True)
        self.assertEqual((meta["version"], meta["parent_version"]), (5, 4))
        stored = ft.model_meta(model)
        self.assertEqual(stored["version"], 5)
        self.assertEqual(stored["sessions"], [sid])
        self.assertEqual(stored["history"][-1]["lines"], len(lines))
        self.assertEqual((model / "model.safetensors").read_text(encoding="utf-8"), "1")
        self.assertTrue((model / ft.TRAIN_META).exists())
        self.assertEqual([p.name for p in model.parent.iterdir()], ["laya-ft"])
        block = "\n".join(self.logs)
        self.assertIn(f"watch: session {sid} (match over: ended_at)", block)
        self.assertIn(f"  lines     {len(lines)} (12 decision points + {len(lines) - 12} augmented)", block)
        self.assertIn("  seconds   ", block)
        self.assertRegex(block, r"held-out  plain \d+\.\d% -> \d+\.\d%, balanced \d+\.\d% -> \d+\.\d% \(test.jsonl, 25 lines\)")
        self.assertIn("  weights   v4 -> v5 in ", block)
        self.assertEqual(watcher.poll(), [])

    def test_base_model_when_no_laya_ft_and_version_starts_at_one(self):
        watcher = self.watcher()
        write_session(self.root, "2026-10-18T12-01-00_a_djin_vs_kaz")
        with mock.patch.object(ft, "base_checkpoint", return_value=Path("hub-snapshot")) as base:
            [(_, meta)] = watcher.poll()
        self.assertEqual(base.call_args[0][0], "convaiinnovations/laya")
        self.assertEqual(meta["version"], 1)
        self.assertEqual(ft.model_version(self.root / "models" / "laya-ft"), 1)

    def test_versions_keep_counting_across_matches(self):
        seed_weights(self.root)
        watcher = self.watcher()
        for minute in ("02", "03"):
            write_session(self.root, f"2026-10-18T12-{minute}-00_a_djin_vs_kaz")
            watcher.poll()
        meta = ft.model_meta(self.root / "models" / "laya-ft")
        self.assertEqual(meta["version"], 2)
        self.assertEqual(len(meta["history"]), 2)

    def test_quiet_recording_with_match_over_counts_as_finished(self):
        seed_weights(self.root)
        watcher = self.watcher()
        sid = "2026-10-18T12-04-00_a_djin_vs_kaz"
        rec = write_session(self.root, sid, ended=False)
        self.assertEqual(watcher.poll(), [])
        self.clock.now += 3
        self.assertEqual(watcher.poll(), [])
        with open(rec, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(build_state([idle(0, 1), idle(1, 1)], 0, 1, sid)) + "\n")
        self.clock.now += 4
        self.assertEqual(watcher.poll(), [])
        self.clock.now += 5.5
        self.assertEqual([s for s, _ in watcher.poll()], [sid])
        self.assertIn("recording quiet for 5 s, last round_end has match_over", "\n".join(self.logs))

    def test_quiet_recording_without_match_over_keeps_waiting(self):
        watcher = self.watcher()
        write_session(self.root, "2026-10-18T12-05-00_a_djin_vs_kaz", ended=False, match_over=False)
        watcher.poll()
        self.clock.now += 30
        self.assertEqual(watcher.poll(), [])
        self.assertEqual(self.trainer.loaded, [])

    def test_sessions_over_at_startup_are_skipped_unless_backfilled(self):
        seed_weights(self.root)
        write_session(self.root, "2026-10-18T11-00-00_a_djin_vs_kaz")
        watcher = self.watcher()
        self.assertEqual(watcher.poll(), [])
        self.assertIn("1 finished or stale session(s)", self.logs[0])
        backfill = self.watcher(backfill=True)
        self.assertEqual([s for s, _ in backfill.poll()], ["2026-10-18T11-00-00_a_djin_vs_kaz"])
        self.assertEqual(self.watcher(backfill=True).poll(), [])

    def test_held_out_test_session_and_empty_sessions_are_never_trained(self):
        watcher = self.watcher()
        write_session(self.root, f"{ft.TEST_SESSION}_sahil_djin_vs_kaz")
        write_session(self.root, "2026-10-18T12-06-00_a_djin_vs_kaz", points=0)
        self.assertEqual([m for _, m in watcher.poll()], [None, None])
        self.assertEqual(self.trainer.loaded, [])
        self.assertIn("held-out test session; never trained on", "\n".join(self.logs))
        self.assertIn("no decision points", "\n".join(self.logs))

    def test_failed_fine_tune_leaves_the_weights_alone(self):
        model = seed_weights(self.root, version=2)

        class Broken(CpuTrainer):
            def train_model(self, *a, **k):
                raise RuntimeError("CUDA out of memory")

        watcher = self.watcher(trainer=Broken())
        write_session(self.root, "2026-10-18T12-07-00_a_djin_vs_kaz")
        self.assertEqual([m for _, m in watcher.poll()], [None])
        self.assertEqual(ft.model_version(model), 2)
        self.assertEqual((model / "model.safetensors").read_text(encoding="utf-8"), "v0")
        self.assertIn("fine-tune failed", self.logs[-1])

    def test_spark_copy_runs_in_the_background_and_failures_are_only_logged(self):
        seed_weights(self.root)
        calls = []

        def runner(cmd, **kw):
            calls.append(cmd)
            return SimpleNamespace(returncode=255, stderr="ssh: connect to host spark: timed out")

        watcher = self.watcher(spark="eric@spark:/data/kumite/")
        watcher.spark.runner = runner
        threads = []
        send = watcher.spark.send
        watcher.spark.send = lambda path: threads.append(send(path)) or threads[-1]
        write_session(self.root, "2026-10-18T12-08-00_a_djin_vs_kaz")
        [(_, meta)] = watcher.poll()
        threads[0].join(2)
        self.assertIsNotNone(meta)
        self.assertEqual(calls[0][0], "scp")
        self.assertEqual(calls[0][-2:], [str(self.root / "finetune" / "incremental" / "2026-10-18T12-08-00_a_djin_vs_kaz.jsonl"),
                                          "eric@spark:/data/kumite/"])
        self.assertTrue(any("spark: scp" in m and "failed (exit 255)" in m for m in self.logs))
        broken = fw.Spark("x@y:z", log=lambda m, **_: self.logs.append(m),
                          runner=lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("scp", 120)))
        broken.send(Path("a.jsonl")).join(2)
        self.assertIn("spark: scp a.jsonl to x@y:z failed", self.logs[-1])

    def test_swap_replaces_the_directory_and_cleans_old_copies(self):
        dst = seed_weights(self.root)
        (dst.parent / "laya-ft.old-1").mkdir()
        tmp = dst.with_name("laya-ft.tmp")
        tmp.mkdir()
        (tmp / "model.safetensors").write_text("new", encoding="utf-8")
        fw.swap_dir(tmp, dst)
        self.assertEqual((dst / "model.safetensors").read_text(encoding="utf-8"), "new")
        self.assertEqual(sorted(p.name for p in dst.parent.iterdir()), ["laya-ft"])

    def test_last_round_end_reads_the_tail(self):
        rec = write_session(self.root, "2026-10-18T12-09-00_a_djin_vs_kaz")
        self.assertTrue(fw.last_round_end(rec)["detail"]["match_over"])
        with mock.patch.object(fw, "TAIL_BYTES", 64):
            self.assertTrue(fw.last_round_end(rec)["detail"]["match_over"])
        with open(rec, "a", encoding="utf-8") as fh:
            fh.write("x" * 200 + "\n")
        with mock.patch.object(fw, "TAIL_BYTES", 64):
            self.assertTrue(fw.last_round_end(rec)["detail"]["match_over"])

    def test_cli_needs_the_exported_test_split(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"DATA_DIR": tmp}):
            with self.assertRaises(SystemExit) as stop:
                ft.main(["watch", "--device", "cpu"])
        self.assertIn("run python -m game.finetune export first", str(stop.exception))

    def test_cli_polls_until_ctrl_c(self):
        polls = []

        def sleep(seconds):
            polls.append(seconds)
            if len(polls) == 2:
                raise KeyboardInterrupt

        args = SimpleNamespace(device="cpu", spark=None, backfill=False)
        with mock.patch.dict(os.environ, {"DATA_DIR": str(self.root)}):
            code = fw.watch(args, log=lambda m, **_: self.logs.append(m), sleep=sleep)
        self.assertEqual((code, polls), (0, [fw.POLL_S, fw.POLL_S]))
        self.assertIn("watch: polling", self.logs[0])
        self.assertIn("1 epoch, top 8 layers, lr 2e-05, batch 16, bf16", self.logs[0])
        self.assertEqual(self.logs[-1], "watch: stopped")


class TrainVersionTest(unittest.TestCase):
    def test_full_train_also_bumps_the_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = seed_weights(root, version=6)
            train = root / "train.jsonl"
            train.write_text("".join(json.dumps(x) + "\n" for x in split_lines()), encoding="utf-8")
            meta = ft.train_laya(train, train, out, base=str(out), epochs=1, device="cpu", trainer=FakeTrainer(), log=lambda *a, **k: None)
            self.assertEqual(meta["version"], 7)
            self.assertEqual(ft.model_version(out), 7)


if __name__ == "__main__":
    unittest.main()
