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


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the Laya fine-tune dataset: state_text -> design 9.4 question labels from decision points, one session held out")
    parser.add_argument("recordings", nargs="*", default=["data/samples"], help="recordings (.jsonl or .zip) or directories; default data/samples")
    parser.add_argument("--heldout", help="session id (or a unique part of it) to hold out; default the latest session")
    parser.add_argument("--out", help=f"output path; default DATA_DIR/finetune/{DEFAULT_OUT}")
    args = parser.parse_args(argv)
    rows, skipped, chosen, out_path = build(args.recordings, args.heldout, args.out)
    report(rows, skipped, chosen, out_path)
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
