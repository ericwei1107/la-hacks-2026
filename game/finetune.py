import argparse
import json
import math
import random
import re
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
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"
TEST_SESSION = "2026-10-18T07-30-06"
VAL_FRACTION = 0.1
VARIANTS = 4
MAX_VARIANTS = 8
MAX_SHARE = 0.65
POOL = 12
SEED = 0
SPLITS = ("train", "val", "test")
OPTIONS = {
    "after_block": ("press", "throw", "block_high", "block_low", "duck", "ss_left", "ss_right", "backdash", "none"),
    "low_defense": ("hit", "blocked", "low_parry", "jumped"),
    "sidestep_dir": ("left", "right", "none"),
    "throw_break": ("break_1", "break_2", "break_12", "none"),
}
OPTION_FAMILIES = {", ".join(v): k for k, v in OPTIONS.items()}
INSTRUCTION = "Which option did the opponent take? Answer with exactly one option name from the list."
DISTANCES = ("touching the bot", "at close range", "at mid range", "far away")
ALLOWED_DISTANCES = {
    "after_block": DISTANCES[:3],
    "low_defense": DISTANCES[:3],
    "sidestep_dir": DISTANCES[1:],
    "throw_break": DISTANCES[:2],
}
HEALTHS = ("is healthy", "has low health", "has critical health")
HEALTH_SENTENCE = re.compile(r"^The (opponent|bot) (is healthy|has low health|has critical health)\b")
FAR_LEAD = re.compile(r"^The bot is far (ahead|behind) on health\.$")
SENTENCE_SPLIT = re.compile(r"(?<=\.)\s+")


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


def family(situation):
    return situation.split(":")[0]


def recording_paths(sources):
    found = []
    for source in sources:
        source = Path(source)
        if source.is_file():
            found.append(source)
            continue
        if not source.is_dir():
            continue
        for path in sorted(source.rglob("*")):
            if "learning" in path.relative_to(source).parts[:-1] or path.name.endswith(".learning.jsonl"):
                continue
            if path.suffix in (".jsonl", ".zip"):
                found.append(path)
    return found


def session_points(path):
    records = load_jsonl(path)
    states = [r for r in records if r.get("t") == "state"]
    if not states:
        return None, [], None
    sid = states[0]["session_id"]
    human = states[0]["human_slot"]
    recorded = [r for r in records if r.get("t") == "event" and r.get("kind") == "decision_point" and r.get("actor") == human]
    if recorded:
        return sid, recorded, "recorded"
    replayed, _ = decision_points(path)
    return sid, replayed, "replayed"


def export_row(ev, origin):
    text = (ev.get("detail") or {}).get("state_text")
    options = OPTIONS.get(family(ev["situation"]))
    if not text or not options or ev["action"] not in options:
        return None
    return {"session_id": ev["session_id"], "round": ev["round"], "frame": ev["frame"], "situation": ev["situation"],
            "action": ev["action"], "text": text, "origin": origin}


def gather(sources, log=print):
    rows = []
    skipped = Counter()
    seen = {}
    for path in recording_paths(sources):
        sid, points, origin = session_points(path)
        if sid is None:
            continue
        if sid in seen:
            log(f"  {path.name}: session {sid} already read from {seen[sid]}; skipped")
            continue
        seen[sid] = path.name
        kept = 0
        for ev in points:
            row = export_row(ev, origin)
            if row is None:
                skipped[(family(ev["situation"]), "no state_text" if not (ev.get("detail") or {}).get("state_text") else ev["action"])] += 1
                continue
            rows.append(row)
            kept += 1
        log(f"  {path.name}: {kept} decision points ({origin}) from {sid}")
    return rows, skipped


def pick_val(groups, fraction=VAL_FRACTION, seed=SEED):
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)
    target = fraction * sum(groups.values())
    chosen, total = set(), 0
    for key in keys:
        if abs(total + groups[key] - target) < abs(total - target):
            chosen.add(key)
            total += groups[key]
    return chosen


def assign_splits(rows, test_session=TEST_SESSION, fraction=VAL_FRACTION, seed=SEED):
    for row in rows:
        row["split"] = "test" if test_session in row["session_id"] else "train"
    if not any(r["split"] == "test" for r in rows):
        raise SystemExit(f"no decision points from test session {test_session}")
    groups = Counter((r["session_id"], r["round"]) for r in rows if r["split"] == "train")
    val = pick_val(groups, fraction, seed)
    for row in rows:
        if row["split"] == "train" and (row["session_id"], row["round"]) in val:
            row["split"] = "val"
    return val


def sentences(text):
    return [s for s in SENTENCE_SPLIT.split(text.strip()) if s]


def shift_distance(parts, situation, step):
    allowed = ALLOWED_DISTANCES[family(situation)]
    for i, part in enumerate(parts):
        for k, words in enumerate(DISTANCES):
            if part.endswith(f" {words}.") and part.startswith("The opponent is "):
                j = k + step
                if words not in allowed or not 0 <= j < len(DISTANCES) or DISTANCES[j] not in allowed:
                    return None
                return parts[:i] + [part[: -len(words) - 1] + DISTANCES[j] + "."] + parts[i + 1:]
    return None


def shift_health(parts, step):
    found = [(i, HEALTH_SENTENCE.match(p)) for i, p in enumerate(parts)]
    found = [(i, m) for i, m in found if m]
    if len(found) != 2 or found[0][1].group(2) != found[1][1].group(2):
        return None
    j = HEALTHS.index(found[0][1].group(2)) + step
    if not 0 <= j < len(HEALTHS):
        return None
    if j > 0 and any(FAR_LEAD.match(p) for p in parts):
        return None
    out = list(parts)
    for i, m in found:
        out[i] = out[i].replace(m.group(2), HEALTHS[j], 1)
    return out


def drop_recent(parts):
    if parts and parts[0].startswith("Recently"):
        return parts[1:]
    return None


def reorder(parts, rng):
    if len(parts) < 2:
        return None
    out = list(parts)
    while out == parts:
        rng.shuffle(out)
    return out


def variants(row, count=VARIANTS, seed=SEED):
    rng = random.Random(f"{seed}:{row['session_id']}:{row['round']}:{row['frame']}:{row['situation']}")
    parts = sentences(row["text"])
    ops = [lambda p: shift_distance(p, row["situation"], -1), lambda p: shift_distance(p, row["situation"], 1),
           lambda p: shift_health(p, -1), lambda p: shift_health(p, 1), drop_recent]
    rng.shuffle(ops)
    seen = {row["text"]}
    out = []
    for op in ops:
        changed = op(parts)
        text = " ".join(changed) if changed else None
        if text and text not in seen and len(out) < count:
            seen.add(text)
            out.append(text)
    tries = 0
    while len(out) < count and tries < 50:
        tries += 1
        changed = reorder(parts, rng)
        text = " ".join(changed) if changed else None
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def prompt(text, situation):
    options = OPTIONS[family(situation)]
    return f"{text}\nOptions: {', '.join(options)}.\n{INSTRUCTION}"


def pair(text, row):
    return {"prompt": prompt(text, row["situation"]), "label": row["action"]}


def take(row, want, seen, seed=SEED):
    got = []
    for text in variants(row, POOL, seed):
        if len(got) >= want:
            break
        line = pair(text, row)
        key = (line["prompt"], line["label"])
        if key not in seen:
            seen.add(key)
            got.append(line)
    return got


def max_majority(minority_lines, cap=MAX_SHARE):
    return math.floor(cap * minority_lines / (1 - cap) + 1e-9)


def minority_count(n_top, n_minority, base=VARIANTS, most=MAX_VARIANTS, cap=MAX_SHARE):
    for k in range(base, most + 1):
        if n_top * (base + 1) <= max_majority(n_minority * (k + 1), cap):
            return k
    return most


def spread(total, n, seed, key):
    order = list(range(n))
    random.Random(f"{seed}:{key}").shuffle(order)
    out = [total // n] * n
    for i in order[: total % n]:
        out[i] += 1
    return out


def balanced_train(train, base=VARIANTS, most=MAX_VARIANTS, cap=MAX_SHARE, seed=SEED):
    seen = {(pair(r["text"], r)["prompt"], r["action"]) for r in train}
    extra = [[] for _ in train]
    for fam in sorted({family(r["situation"]) for r in train}):
        idx = [i for i, r in enumerate(train) if family(r["situation"]) == fam]
        counts = Counter(train[i]["action"] for i in idx)
        top = min(counts, key=lambda a: (-counts[a], a))
        majority = [i for i in idx if train[i]["action"] == top]
        minority = [i for i in idx if train[i]["action"] != top]
        if not minority:
            for i in majority:
                extra[i] = take(train[i], base, seen, seed)
            continue
        k = minority_count(len(majority), len(minority), base, most, cap)
        for i in minority:
            extra[i] = take(train[i], k, seen, seed)
        minority_lines = len(minority) + sum(len(extra[i]) for i in minority)
        room = max(0, min(base * len(majority), max_majority(minority_lines, cap) - len(majority)))
        for i, want in zip(majority, spread(room, len(majority), seed, fam)):
            extra[i] = take(train[i], want, seen, seed)
    lines = []
    for row, more in zip(train, extra):
        lines.append(pair(row["text"], row))
        lines += more
    return lines


def export_lines(rows, count=VARIANTS, seed=SEED, most=MAX_VARIANTS, cap=MAX_SHARE):
    out = {name: [pair(r["text"], r) for r in rows if r["split"] == name] for name in SPLITS}
    out["train"] = balanced_train([r for r in rows if r["split"] == "train"], count, most, cap, seed)
    return out


def line_family(line):
    options = line["prompt"].rsplit("\nOptions: ", 1)[1].split(".\n", 1)[0]
    return OPTION_FAMILIES[options]


def label_counts(lines):
    out = {}
    for line in lines:
        out.setdefault(line_family(line), Counter())[line["label"]] += 1
    return out


def top_share(counts):
    label = min(counts, key=lambda a: (-counts[a], a))
    return label, counts[label] / sum(counts.values())


def export(sources, out_dir, test_session=TEST_SESSION, fraction=VAL_FRACTION, count=VARIANTS, seed=SEED, log=print,
           most=MAX_VARIANTS, cap=MAX_SHARE):
    rows, skipped = gather(sources, log)
    val = assign_splits(rows, test_session, fraction, seed)
    lines = export_lines(rows, count, seed, most, cap)
    paths = {name: write(lines[name], Path(out_dir) / f"{name}.jsonl") for name in SPLITS}
    return rows, skipped, val, lines, paths


def export_report(rows, skipped, val, lines, paths, log=print):
    train_rows = sum(1 for r in rows if r["split"] in ("train", "val"))
    for name in SPLITS:
        part = [r for r in rows if r["split"] == name]
        sessions = sorted({r["session_id"] for r in part})
        extra = f" ({len(part)} originals + {len(lines[name]) - len(part)} augmented)" if name == "train" else ""
        log(f"{name}: {len(lines[name])} lines{extra} from {len(sessions)} session(s) -> {paths[name]}")
        by_family = Counter(family(r["situation"]) for r in part)
        shares = label_counts(lines[name])
        for fam in OPTIONS:
            if by_family[fam]:
                actions = Counter(r["action"] for r in part if family(r["situation"]) == fam)
                label, share = top_share(shares[fam])
                log(f"  {fam:<13} {by_family[fam]:>4} originals, {sum(shares[fam].values()):>5} lines, top {label} {share:.0%}  "
                    + ", ".join(f"{a} {n}" for a, n in actions.most_common()))
    val_n = sum(1 for r in rows if r["split"] == "val")
    log(f"val: {len(val)} (session, round) groups, {val_n}/{train_rows} pre-augmentation train examples "
        f"({val_n / max(train_rows, 1):.1%})")
    if skipped:
        log("skipped: " + ", ".join(f"{s}/{a} {n}" for (s, a), n in skipped.most_common()))
    log("samples:")
    for name in SPLITS:
        if lines[name]:
            log(f"  {name}: " + json.dumps(lines[name][0]))


def cmd_export(args):
    sources = args.sources or [str(data_dir() / "recordings"), str(SAMPLES_DIR)]
    out_dir = Path(args.out_dir) if args.out_dir else data_dir() / "finetune"
    print(f"reading {', '.join(sources)}")
    result = export(sources, out_dir, args.test_session, args.val_fraction, args.variants, args.seed)
    export_report(*result)
    return 0 if result[0] else 1


def majority_labels(train_lines):
    return {fam: top_share(counts)[0] for fam, counts in label_counts(train_lines).items()}


def score(lines, majority):
    by_class = {}
    for line in lines:
        fam = line_family(line)
        hits = by_class.setdefault((fam, line["label"]), [0, 0])
        hits[0] += line["label"] == majority.get(fam)
        hits[1] += 1
    out = {}
    for fam in OPTIONS:
        classes = [v for (f, _), v in by_class.items() if f == fam]
        if classes:
            out[fam] = {"n": sum(v[1] for v in classes), "accuracy": sum(v[0] for v in classes) / sum(v[1] for v in classes),
                        "balanced": sum(v[0] / v[1] for v in classes) / len(classes)}
    classes = list(by_class.values())
    if classes:
        out["overall"] = {"n": sum(v[1] for v in classes), "accuracy": sum(v[0] for v in classes) / sum(v[1] for v in classes),
                          "balanced": sum(v[0] / v[1] for v in classes) / len(classes)}
    return out


def cmd_baseline(args):
    folder = Path(args.dir) if args.dir else data_dir() / "finetune"
    lines = {name: read_rows(folder / f"{name}.jsonl") for name in SPLITS}
    if not lines["train"]:
        raise SystemExit(f"no training lines in {folder}; run python -m game.finetune export first")
    majority = majority_labels(lines["train"])
    print(f"majority-class predictor from {folder / 'train.jsonl'}: " + ", ".join(f"{f} -> {majority[f]}" for f in OPTIONS if f in majority))
    print("balanced accuracy is the mean recall over the labels present; overall balanced is over every (situation, label) present")
    for name in ("val", "test"):
        print(f"{name}:")
        for key, row in score(lines[name], majority).items():
            print(f"  {key:<13} n={row['n']:<4} accuracy {row['accuracy']:.1%}  balanced {row['balanced']:.1%}")
    print("test label counts:")
    counts = label_counts(lines["test"])
    for fam in OPTIONS:
        if fam in counts:
            print(f"  {fam:<13} " + ", ".join(f"{a} {n}" for a, n in counts[fam].most_common()))
    return 0


COMMANDS = ("build", "export", "baseline", "eval", "bench", "train")


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
    e = sub.add_parser("export", help="decision points -> {prompt, label} train/val/test jsonl with a held-out test session")
    e.add_argument("sources", nargs="*", help="recordings or directories; default DATA_DIR/recordings and data/samples")
    e.add_argument("--test-session", default=TEST_SESSION, help="session id (or a unique part) held out as the test split")
    e.add_argument("--val-fraction", type=float, default=VAL_FRACTION)
    e.add_argument("--variants", type=int, default=VARIANTS, help="augmented variants per training example")
    e.add_argument("--seed", type=int, default=SEED)
    e.add_argument("--out-dir", help="default DATA_DIR/finetune")
    bl = sub.add_parser("baseline", help="majority-class accuracy and balanced accuracy on the exported val and test splits")
    bl.add_argument("--dir", help="folder with train/val/test.jsonl; default DATA_DIR/finetune")
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
    return {"build": cmd_build, "export": cmd_export, "baseline": cmd_baseline, "eval": cmd_eval, "bench": cmd_bench, "train": cmd_train}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
