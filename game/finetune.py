import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from game.recorder import data_dir, dumps
from game.summarize import find_session, load_jsonl, replay

QUESTIONS = {
    "opp_presses": "Is the opponent likely to attack immediately?",
    "opp_ducks": "Is the opponent likely to duck or block low?",
    "opp_steps": "Is the opponent likely to sidestep?",
    "opp_passive": "Is the opponent holding back and waiting?",
}
AFTER_BLOCK_LABELS = {
    "press": {"opp_presses": True, "opp_ducks": False, "opp_steps": False, "opp_passive": False},
    "throw": {"opp_presses": True, "opp_ducks": False, "opp_steps": False, "opp_passive": False},
    "duck": {"opp_presses": False, "opp_ducks": True, "opp_steps": False, "opp_passive": True},
    "block_low": {"opp_presses": False, "opp_ducks": True, "opp_steps": False, "opp_passive": True},
    "block_high": {"opp_presses": False, "opp_ducks": False, "opp_steps": False, "opp_passive": True},
    "none": {"opp_presses": False, "opp_ducks": False, "opp_steps": False, "opp_passive": True},
    "backdash": {"opp_presses": False, "opp_ducks": False, "opp_steps": False, "opp_passive": False},
    "ss_left": {"opp_presses": False, "opp_ducks": False, "opp_steps": True, "opp_passive": False},
    "ss_right": {"opp_presses": False, "opp_ducks": False, "opp_steps": True, "opp_passive": False},
}
LOW_DEFENSE_LABELS = {
    "blocked": {"opp_ducks": True},
    "hit": {"opp_ducks": False},
    "jumped": {"opp_ducks": False},
    "low_parry": {"opp_ducks": False},
}
SIDESTEP_LABELS = {
    "left": {"opp_steps": True},
    "right": {"opp_steps": True},
    "none": {"opp_steps": False},
}
DEFAULT_OUT = "laya_decisions.jsonl"


def labels(situation, action):
    if situation.startswith("after_block:"):
        table = AFTER_BLOCK_LABELS
    elif situation == "low_defense":
        table = LOW_DEFENSE_LABELS
    elif situation == "sidestep_dir":
        table = SIDESTEP_LABELS
    else:
        return {}
    return dict(table.get(action, {}))


def session_meta(path, sid):
    found = find_session(path, sid)
    return json.loads(found[1]) if found else {}


def decision_points(path):
    records = load_jsonl(path)
    states = [r for r in records if r.get("t") == "state"]
    if not states:
        return [], {}
    sid = states[0]["session_id"]
    meta = session_meta(path, sid)
    human = states[0]["human_slot"]
    events = replay(states, meta.get("mode", "practice"))
    return [e for e in events if e["kind"] == "decision_point" and e.get("actor") == human], meta


def example(ev, meta, source):
    detail = ev.get("detail") or {}
    text = detail.get("state_text")
    questions = labels(ev["situation"], ev["action"])
    if not text or not questions:
        return None
    return {
        "session_id": ev["session_id"],
        "source": source,
        "round": ev["round"],
        "frame": ev["frame"],
        "start_frame": detail.get("start_frame"),
        "situation": ev["situation"],
        "action": ev["action"],
        "correct": bool(detail.get("correct")),
        "human_character": meta.get("human_character"),
        "bot_character": meta.get("bot_character"),
        "difficulty": meta.get("difficulty"),
        "text": text,
        "questions": questions,
    }


def collect(paths):
    rows = []
    skipped = Counter()
    for path in paths:
        points, meta = decision_points(path)
        source = Path(path).name
        for ev in points:
            row = example(ev, meta, source)
            if row is None:
                skipped[(ev["situation"].split(":")[0], ev["action"])] += 1
                continue
            rows.append(row)
    return rows, skipped


def pick_heldout(rows, heldout=None):
    sessions = sorted({r["session_id"] for r in rows})
    if not sessions:
        return None
    if heldout:
        matches = sorted({r["session_id"] for r in rows if heldout in r["session_id"] or heldout in r["source"]})
        if not matches:
            raise SystemExit(f"no session or recording matches --heldout {heldout}; sessions: {sessions}")
        return matches[0]
    return sessions[-1]


def split(rows, heldout=None):
    chosen = pick_heldout(rows, heldout)
    for row in rows:
        row["split"] = "heldout" if row["session_id"] == chosen else "train"
    return chosen


def majority_baseline(rows):
    train = [r for r in rows if r["split"] == "train"]
    held = [r for r in rows if r["split"] == "heldout"]
    out = {}
    for q in QUESTIONS:
        votes = Counter(r["questions"][q] for r in train if q in r["questions"])
        tests = [r["questions"][q] for r in held if q in r["questions"]]
        if not votes or not tests:
            out[q] = {"majority": None, "n_train": sum(votes.values()), "n_heldout": len(tests), "accuracy": None}
            continue
        guess = votes.most_common(1)[0][0]
        acc = sum(1 for t in tests if t == guess) / len(tests)
        out[q] = {"majority": guess, "n_train": sum(votes.values()), "n_heldout": len(tests), "accuracy": round(acc, 4)}
    return out


def write(rows, out_path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(dumps(row) + "\n")
    return out_path


def find_recordings(paths):
    found = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            by_stem = {}
            for x in sorted(p.iterdir()):
                if x.suffix == ".zip" or (x.suffix == ".jsonl" and not x.name.endswith(".learning.jsonl")):
                    if x.stem not in by_stem or x.suffix == ".zip":
                        by_stem[x.stem] = x
            found += list(by_stem.values())
        else:
            found.append(p)
    return found


def build(paths, heldout=None, out_path=None):
    rows, skipped = collect(find_recordings(paths))
    chosen = split(rows, heldout)
    out_path = Path(out_path) if out_path else data_dir() / "finetune" / DEFAULT_OUT
    write(rows, out_path)
    return rows, skipped, chosen, out_path


def report(rows, skipped, chosen, out_path):
    print(f"wrote {out_path}: {len(rows)} examples, held-out session {chosen}")
    if skipped:
        print("  skipped (no question label): " + ", ".join(f"{s}/{a} {n}" for (s, a), n in skipped.most_common()))
    train_n = sum(1 for r in rows if r["split"] == "train")
    if train_n < len(rows) - train_n:
        print(f"  warning: only {train_n} training examples; pass --heldout <session> to hold out a smaller session")
    for name in ("train", "heldout"):
        part = [r for r in rows if r["split"] == name]
        sits = Counter(r["situation"].split(":")[0] for r in part)
        sessions = sorted({r["session_id"] for r in part})
        print(f"  {name}: {len(part)} examples from {len(sessions)} session(s): " + ", ".join(f"{s} {n}" for s, n in sits.most_common()))
        for q in QUESTIONS:
            votes = Counter(r["questions"][q] for r in part if q in r["questions"])
            if votes:
                print(f"    {q:<12} yes {votes[True]:<4} no {votes[False]}")
    print("majority-class baseline on the held-out session (the floor the fine-tune must beat):")
    for q, row in majority_baseline(rows).items():
        acc = "n/a" if row["accuracy"] is None else f"{row['accuracy']:.0%}"
        print(f"  {q:<12} guess {str(row['majority']).lower():<5} accuracy {acc} (train {row['n_train']}, held-out {row['n_heldout']})")


def laya_row(row):
    return {
        "state": row["text"],
        "questions": {q: {"type": "noul", "instructions": QUESTIONS[q]} for q in row["questions"]},
        "expected": {q: bool(v) for q, v in row["questions"].items()},
    }


def write_laya(rows, out_dir):
    out_dir = Path(out_dir)
    paths = {}
    for name in ("train", "heldout"):
        part = [laya_row(r) for r in rows if r["split"] == name]
        paths[name] = write(part, out_dir / f"{name}.jsonl")
    return paths


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate(model, rows, threshold=0.5, batch_size=16):
    held = [r for r in rows if r.get("split", "heldout") == "heldout"]
    if not held:
        return {}
    answers = model.predict_batch([r["text"] for r in held], batch_size=batch_size)
    out = {}
    for q in QUESTIONS:
        pairs = [(a[q]["p"], r["questions"][q]) for a, r in zip(answers, held) if q in r["questions"] and a[q]["p"] is not None]
        if not pairs:
            out[q] = {"n": 0, "accuracy": None}
            continue
        correct = sum(1 for p, label in pairs if (p >= threshold) == label)
        out[q] = {"n": len(pairs), "accuracy": round(correct / len(pairs), 4), "mean_p_yes": round(sum(p for p, _ in pairs) / len(pairs), 4)}
    scored = [v for v in out.values() if v["accuracy"] is not None]
    out["overall"] = {"n": sum(v["n"] for v in scored),
                      "accuracy": round(sum(v["accuracy"] * v["n"] for v in scored) / sum(v["n"] for v in scored), 4) if scored else None}
    return out


def print_eval(label, result, baseline=None):
    print(f"{label}:")
    for q in QUESTIONS:
        row = result.get(q, {"n": 0, "accuracy": None})
        acc = "n/a" if row["accuracy"] is None else f"{row['accuracy']:.0%}"
        base = ""
        if baseline and baseline.get(q, {}).get("accuracy") is not None:
            base = f"  (majority {baseline[q]['accuracy']:.0%})"
        print(f"  {q:<12} accuracy {acc:<5} n={row['n']}{base}")
    overall = result.get("overall", {})
    if overall.get("accuracy") is not None:
        print(f"  overall      accuracy {overall['accuracy']:.0%} n={overall['n']}")


def cmd_build(args):
    rows, skipped, chosen, out_path = build(args.recordings, args.heldout, args.out)
    report(rows, skipped, chosen, out_path)
    paths = write_laya(rows, out_path.parent)
    print(f"laya format: {paths['train']} and {paths['heldout']} ({{state, questions, expected}} rows for laya.train.finetune)")
    return 0 if rows else 1


def load_dataset(path):
    rows = read_rows(path or data_dir() / "finetune" / DEFAULT_OUT)
    if not rows:
        raise SystemExit("no examples; run python -m game.finetune build first")
    return rows


def cmd_eval(args):
    from game.laya import Laya
    rows = load_dataset(args.dataset)
    model = Laya(args.model, args.device)
    model.warmup()
    print(f"loaded {args.model} on {model.device or 'auto'} in {model.load_seconds:.1f} s, warm-up {model.warmup_seconds:.2f} s")
    result = evaluate(model, rows, args.threshold)
    print_eval(f"{args.model} on the held-out session", result, majority_baseline(rows))
    return 0


def cmd_bench(args):
    from game.laya import Laya
    rows = load_dataset(args.dataset)
    model = Laya(args.model, args.device)
    stats = model.bench([r["text"] for r in rows], args.rounds)
    print(f"loaded {args.model} on {model.device or 'auto'} in {model.load_seconds:.1f} s, warm-up {model.warmup_seconds:.2f} s")
    print(f"{len(QUESTIONS)}-question batch, {stats['n']} calls: p50 {stats['p50_ms']} ms, p95 {stats['p95_ms']} ms, mean {stats['mean_ms']} ms "
          f"(budget: 4 frames = 66.7 ms)")
    return 0


def cmd_train(args):
    from laya.train import TrainConfig, finetune
    base = Path(args.base)
    if not base.is_dir():
        from huggingface_hub import snapshot_download
        print(f"downloading {args.base} to {args.local_base}")
        base = Path(snapshot_download(args.base, local_dir=args.local_base))
    train_path = Path(args.train or data_dir() / "finetune" / "train.jsonl")
    held_path = Path(args.heldout or data_dir() / "finetune" / "heldout.jsonl")
    config = TrainConfig(epochs=args.epochs, micro_batch=args.micro_batch, grad_accum=args.grad_accum, seed=args.seed,
                         eval_data=str(held_path) if held_path.exists() else None)
    summary = finetune(str(train_path), str(base), args.out, config, device=args.device or "auto")
    print(json.dumps(summary, indent=2, default=str))
    print(f"fine-tuned checkpoint in {args.out}; evaluate with: python -m game.finetune eval --model {args.out}")
    return 0


COMMANDS = ("build", "eval", "bench", "train")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in COMMANDS and not argv[0] in ("-h", "--help"):
        argv = ["build"] + argv
    parser = argparse.ArgumentParser(description="Laya fine-tune pipeline: build the dataset from decision points, evaluate, benchmark, train (laptop fallback)")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="decision points -> state_text with design 9.4 question labels, one session held out")
    b.add_argument("recordings", nargs="*", default=["data/samples"], help="recordings (.jsonl or .zip) or directories; default data/samples")
    b.add_argument("--heldout", help="session id or recording name (or a unique part) to hold out; default the latest session")
    b.add_argument("--out", help=f"output path; default DATA_DIR/finetune/{DEFAULT_OUT}")
    for name, help_ in (("eval", "accuracy of a Laya checkpoint on the held-out session"), ("bench", "p50/p95 latency of a 4-question batch")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--model", default="convaiinnovations/laya", help="HF repo id or local checkpoint directory")
        p.add_argument("--device", help="cuda, cpu; default Laya's own order (cuda first)")
        p.add_argument("--dataset", help=f"default DATA_DIR/finetune/{DEFAULT_OUT}")
        if name == "eval":
            p.add_argument("--threshold", type=float, default=0.5)
        else:
            p.add_argument("--rounds", type=int, default=50)
    t = sub.add_parser("train", help="fine-tune on the laptop with laya.train.finetune (fallback when Veri is unavailable)")
    t.add_argument("--base", default="convaiinnovations/laya", help="HF repo id or local checkpoint directory")
    t.add_argument("--local-base", default=str(data_dir() / "finetune" / "laya_base"), help="where a downloaded base checkpoint is kept")
    t.add_argument("--out", default=str(data_dir() / "finetune" / "laya_tekken"))
    t.add_argument("--train")
    t.add_argument("--heldout")
    t.add_argument("--device")
    t.add_argument("--epochs", type=int, default=4)
    t.add_argument("--micro-batch", type=int, default=4)
    t.add_argument("--grad-accum", type=int, default=8)
    t.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    return {"build": cmd_build, "eval": cmd_eval, "bench": cmd_bench, "train": cmd_train}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
