import contextlib
import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

from game import finetune as ft
from game.recorder import data_dir

POLL_S = 1.0
QUIET_S = 5.0
EPOCHS = 1
LAYERS = 8
LR = 2e-5
BATCH = 16
BUDGET_S = 40.0
INCREMENTAL = "incremental"
TAIL_BYTES = 1 << 20
SCP_TIMEOUT_S = 120
HISTORY_KEEP = 50
STALE_S = 60.0


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def recording_for(meta, root):
    sid = meta.get("session_id", "")
    found = []
    if meta.get("recording"):
        rec = Path(meta["recording"])
        found += [rec, root / "recordings" / rec.name]
    found += [root / "recordings" / f"{sid}.jsonl", root / "recordings" / f"{sid}.zip"]
    for path in found:
        if path.is_file():
            return path
    return None


def last_round_end(path):
    path = Path(path)
    if path.suffix != ".jsonl":
        return None
    size = path.stat().st_size
    with open(path, "rb") as fh:
        for start in ([max(0, size - TAIL_BYTES), 0] if size > TAIL_BYTES else [0]):
            fh.seek(start)
            lines = fh.read().decode("utf-8", errors="replace").splitlines()
            for line in reversed(lines[1:] if start else lines):
                if '"round_end"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("t") == "event" and rec.get("kind") == "round_end":
                    return rec
    return None


def session_lines(recording, seed=ft.SEED):
    rows, _ = ft.gather([recording], log=lambda *a, **k: None)
    for row in rows:
        row["split"] = "train"
    return ft.balanced_train(rows, seed=seed), rows


def bf16(device):
    if str(getattr(device, "type", device)).startswith("cuda"):
        import torch
        return torch.autocast("cuda", dtype=torch.bfloat16)
    return contextlib.nullcontext()


def swap_dir(tmp, dst):
    tmp, dst = Path(tmp), Path(dst)
    for stale in dst.parent.glob(dst.name + ".old-*"):
        shutil.rmtree(stale, ignore_errors=True)
    old = dst.with_name(f"{dst.name}.old-{time.time_ns()}")
    if dst.exists():
        for attempt in range(5):
            try:
                dst.rename(old)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2)
    tmp.rename(dst)
    shutil.rmtree(old, ignore_errors=True)


def shrink_frozen(model, device):
    if not str(getattr(device, "type", device)).startswith("cuda"):
        return 0
    import torch
    moved = 0
    for param in model.parameters():
        if not param.requires_grad and param.dtype == torch.float32:
            param.data = param.data.to(torch.bfloat16)
            moved += param.numel()
    return moved


def free_cuda():
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def incremental_train(lines, test_lines, prior_lines, model_dir, session_id, device="cuda", trainer=None, seed=ft.SEED,
                      precision=bf16, log=print):
    from game.laya import MODEL, has_weights
    if trainer is None:
        import laya.train as trainer
    model_dir = Path(model_dir)
    times = {}
    started = time.perf_counter()
    current = has_weights(model_dir)
    base = str(model_dir) if current else MODEL
    old_meta = ft.model_meta(model_dir) if current else {}
    old_version = ft.model_version(model_dir) if current else 0
    dev = trainer.resolve_device(device)
    model, tok, cfg = trainer.load_checkpoint(str(ft.base_checkpoint(base)))
    max_len, head_max_len = cfg.get("max_len", 512), cfg.get("head_max_len", 192)
    items, _ = trainer.items_from_rows(tok, ft.yes_no_rows(lines), max_len, head_max_len)
    if not items:
        raise ValueError("no yes/no training items in this session's lines")
    ft.freeze_lower(model, LAYERS)
    if precision is bf16:
        shrink_frozen(model, dev)
    model.to(dev)
    t_items, spans = ft.val_items(trainer, tok, test_lines, max_len, head_max_len)
    prior = ft.label_counts(prior_lines)
    temperature = float((cfg.get("temperature_by_options") or {}).get("noul:2", 1.0))
    times["load"] = time.perf_counter() - started

    def test_score():
        with precision(dev):
            records = trainer.calibration_records(model, tok, t_items, dev, max_len, head_max_len, batch_size=BATCH) if t_items else []
        model.train()
        return ft.score_predictions(test_lines, ft.val_predictions(test_lines, spans, records, temperature, prior)).get("overall", {})

    mark = time.perf_counter()
    before = test_score()
    config = trainer.TrainConfig(epochs=EPOCHS, micro_batch=BATCH, grad_accum=1, encoder_lr=LR, head_lr=LR, seed=seed, log_every=0,
                                 amp=False, gradient_checkpointing=False)
    losses = []
    with precision(dev):
        trainer.train_model(model, tok, items, config, dev, max_len, head_max_len, on_epoch_end=lambda epoch, loss: losses.append(float(loss)))
    times["train"] = time.perf_counter() - mark
    mark = time.perf_counter()
    after = test_score()
    times["eval"] = time.perf_counter() - mark
    mark = time.perf_counter()
    version = old_version + 1
    tmp = model_dir.with_name(model_dir.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    trainer.save_checkpoint(model, tok, dict(cfg, max_len=max_len, head_max_len=head_max_len), str(tmp))
    if current and (model_dir / ft.TRAIN_META).exists():
        shutil.copy2(model_dir / ft.TRAIN_META, tmp / ft.TRAIN_META)
    entry = {"version": version, "session_id": session_id, "lines": len(lines), "items": len(items),
             "loss": round(losses[-1], 4) if losses else None,
             "test_before": before, "test_after": after, "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    history = (old_meta.get("history") or [])[-(HISTORY_KEEP - 1):] + [entry]
    sessions = list(old_meta.get("sessions") or []) + [session_id]
    meta = {"version": version, "kind": "incremental", "parent_version": old_version, "parent": base, "session_id": session_id,
            "epochs": EPOCHS, "train_layers": LAYERS, "lr": LR, "batch": BATCH, "precision": "bf16" if precision is bf16 else "custom",
            "device": str(dev), "test": {"before": before, "after": after}, "trained_at": entry["trained_at"],
            "sessions": sessions, "history": history}
    ft.write_atomic(tmp / ft.MODEL_META, meta)
    del model
    free_cuda()
    swap_dir(tmp, model_dir)
    times["save"] = time.perf_counter() - mark
    meta["seconds"] = round(time.perf_counter() - started, 1)
    meta["times"] = {k: round(v, 1) for k, v in times.items()}
    return meta


def pct(row, key):
    value = (row or {}).get(key)
    return "n/a" if value is None else f"{value:.1%}"


def report(sid, reason, lines, rows, path, meta, test_n, log=print):
    test = meta["test"]
    times = ", ".join(f"{k} {v:.1f}" for k, v in meta["times"].items())
    log(f"watch: session {sid} (match over: {reason})")
    log(f"  lines     {len(lines)} ({len(rows)} decision points + {len(lines) - len(rows)} augmented) -> {path}")
    log(f"  seconds   {meta['seconds']:.1f} ({times})" + (f"  over the {BUDGET_S:.0f} s budget" if meta["seconds"] > BUDGET_S else ""))
    log(f"  held-out  plain {pct(test['before'], 'accuracy')} -> {pct(test['after'], 'accuracy')}, "
        f"balanced {pct(test['before'], 'balanced')} -> {pct(test['after'], 'balanced')} (test.jsonl, {test_n} lines)")
    log(f"  weights   v{meta['parent_version']} -> v{meta['version']} in {meta['out']}", flush=True)


class Spark:
    def __init__(self, dest, log=print, runner=subprocess.run):
        self.dest = dest
        self.log = log
        self.runner = runner

    def send(self, path):
        thread = threading.Thread(target=self._send, args=(Path(path),), name="spark-scp", daemon=True)
        thread.start()
        return thread

    def _send(self, path):
        try:
            done = self.runner(["scp", "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", str(path), self.dest],
                               capture_output=True, text=True, timeout=SCP_TIMEOUT_S)
        except (OSError, subprocess.SubprocessError) as e:
            self.log(f"spark: scp {path.name} to {self.dest} failed: {e}", flush=True)
            return
        if done.returncode:
            self.log(f"spark: scp {path.name} to {self.dest} failed (exit {done.returncode}): {(done.stderr or '').strip()}", flush=True)
        else:
            self.log(f"spark: copied {path.name} to {self.dest}", flush=True)


class Watcher:
    def __init__(self, root=None, device="cuda", spark=None, backfill=False, quiet=QUIET_S, trainer=None, precision=bf16,
                 clock=time.monotonic, log=print, model_dir=None):
        self.root = Path(root) if root is not None else data_dir()
        self.device = device
        self.spark = Spark(spark, log) if spark else None
        self.quiet = quiet
        self.trainer = trainer
        self.precision = precision
        self.clock = clock
        self.log = log
        self.model_dir = Path(model_dir) if model_dir is not None else self.root / "models" / "laya-ft"
        self.folder = self.root / "finetune"
        self.out_dir = self.folder / INCREMENTAL
        self.done = set()
        self.growth = {}
        self.checked = {}
        if not backfill:
            skipped = [sid for sid, meta in self.sessions() if self.over(sid, meta) or self.stale(meta)]
            self.done.update(skipped)
            if skipped:
                log(f"watch: {len(skipped)} finished or stale session(s) already in {self.root / 'sessions'}; skipped "
                    f"(--backfill trains on the ones not in {self.model_dir.name}/{ft.MODEL_META} yet)")
        else:
            self.done.update(ft.model_meta(self.model_dir).get("sessions") or [])

    def sessions(self):
        out = []
        for path in sorted((self.root / "sessions").glob("*.json")):
            meta = read_json(path)
            if isinstance(meta, dict) and meta.get("session_id"):
                out.append((meta["session_id"], meta))
        return out

    def stale(self, meta):
        recording = recording_for(meta, self.root)
        return recording is None or time.time() - recording.stat().st_mtime > STALE_S

    def over(self, sid, meta):
        if meta.get("ended_at"):
            return "ended_at"
        recording = recording_for(meta, self.root)
        if recording is None:
            return None
        size = recording.stat().st_size
        now = self.clock()
        seen = self.growth.get(sid)
        if seen is None or seen[0] != size:
            self.growth[sid] = (size, now)
            return None
        if now - seen[1] < self.quiet:
            return None
        if self.checked.get(sid) != size:
            self.checked[sid] = size
            end = last_round_end(recording)
            if end and (end.get("detail") or {}).get("match_over"):
                return "recording quiet for 5 s, last round_end has match_over"
        return None

    def poll(self):
        handled = []
        for sid, meta in self.sessions():
            if sid in self.done:
                continue
            reason = self.over(sid, meta)
            if not reason:
                continue
            self.done.add(sid)
            handled.append((sid, self.process(sid, meta, reason)))
        return handled

    def process(self, sid, meta, reason):
        if ft.TEST_SESSION in sid:
            self.log(f"watch: session {sid} is the held-out test session; never trained on", flush=True)
            return None
        recording = recording_for(meta, self.root)
        if recording is None:
            self.log(f"watch: session {sid} is over but its recording is missing; skipped", flush=True)
            return None
        try:
            lines, rows = session_lines(recording)
        except Exception as e:
            self.log(f"watch: session {sid}: could not read decision points from {recording} ({e!r}); skipped", flush=True)
            return None
        if not lines:
            self.log(f"watch: session {sid} has no decision points; nothing to train on", flush=True)
            return None
        path = ft.write(lines, self.out_dir / f"{sid}.jsonl")
        if self.spark is not None:
            self.spark.send(path)
        test_lines = ft.read_rows(self.folder / "test.jsonl") if (self.folder / "test.jsonl").exists() else []
        prior_lines = ft.read_rows(self.folder / "train.jsonl") if (self.folder / "train.jsonl").exists() else lines
        try:
            meta = incremental_train(lines, test_lines, prior_lines, self.model_dir, sid, self.device, self.trainer,
                                     precision=self.precision, log=self.log)
        except (SystemExit, Exception) as e:
            self.log(f"watch: session {sid}: fine-tune failed ({e!r}); weights unchanged", flush=True)
            return None
        meta["out"] = str(self.model_dir)
        report(sid, reason, lines, rows, path, meta, len(test_lines), self.log)
        return meta


def watch(args, log=print, sleep=time.sleep):
    watcher = Watcher(device=args.device, spark=args.spark, backfill=args.backfill, log=log)
    test = watcher.folder / "test.jsonl"
    if not test.exists():
        raise SystemExit(f"no {test}; run python -m game.finetune export first (it writes the held-out test split)")
    from game.laya import has_weights
    start = f"v{ft.model_version(watcher.model_dir)} in {watcher.model_dir}" if has_weights(watcher.model_dir) else "the base model (no laya-ft yet)"
    log(f"watch: polling {watcher.root / 'sessions'} every {POLL_S:.0f} s; each finished match fine-tunes {start} "
        f"({EPOCHS} epoch, top {LAYERS} layers, lr {LR:g}, batch {BATCH}, bf16 on {args.device}); held-out {test} "
        f"({len(ft.read_rows(test))} lines)" + (f"; incremental jsonl also goes to {args.spark}" if args.spark else "") + ". Ctrl+C to stop",
        flush=True)
    try:
        while True:
            watcher.poll()
            sleep(POLL_S)
    except KeyboardInterrupt:
        log("watch: stopped", flush=True)
    return 0
