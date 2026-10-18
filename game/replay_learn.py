import argparse
import copy
import json
import sys
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from game.detect import Detector
from game.hotloop import fmt_event
from game.options import load_options
from game.state import Tracker
from game.summarize import CONTRACTS, find_session, load_jsonl

EVENT_V = Draft202012Validator(json.loads((CONTRACTS / "event.schema.json").read_text()), format_checker=FormatChecker())


def subject_slot(states, subject):
    human = states[0]["human_slot"] if states else 0
    if subject in ("human", None):
        return human
    if subject == "bot":
        return 1 - human
    return int(subject)


def run_detector(states, subject="human", mode="practice", rounds_to_win=3, table=None):
    versus = mode == "versus"
    tracker = Tracker(states[0]["session_id"] if states else "", timeouts=versus, rounds_to_win=rounds_to_win if versus else None)
    slot = subject_slot(states, subject)
    detector = None
    events, decisions = [], []
    for raw in states:
        if tracker.match_over and tracker.prev is not None and raw["frame"] < tracker.prev["frame"]:
            break
        state = copy.deepcopy(raw)
        evs = tracker.step(state)
        if detector is None:
            opp = state["players"][1 - slot]["character"]
            detector = Detector(slot, table if table is not None else load_options(opp)[0])
        found = detector.step(state, evs)
        events.extend(evs)
        decisions.extend(found)
    events.extend(tracker.finish())
    return events, decisions, detector


def situation_table(decisions):
    rows = {}
    for ev in decisions:
        row = rows.setdefault(ev["situation"], {"n": 0, "correct": 0, "actions": Counter()})
        row["n"] += 1
        row["correct"] += bool((ev.get("detail") or {}).get("correct"))
        row["actions"][ev["action"]] += 1
    return rows


def print_table(rows):
    if not rows:
        print("  (no situations detected)")
    for situation in sorted(rows):
        row = rows[situation]
        acts = ", ".join(f"{a} {n}" for a, n in row["actions"].most_common())
        print(f"  {situation:<24} n={row['n']:<4} correct {row['correct'] / row['n']:.0%}  actions: {acts}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Replay a recording through the tracker and the situation detector (no game needed)")
    parser.add_argument("recording")
    parser.add_argument("--subject", default="human", choices=("human", "bot"), help="whose responses to detect (bot = mirror check)")
    parser.add_argument("--sentences", type=int, default=3, help="how many state_text samples to print")
    parser.add_argument("--all", action="store_true", help="print every decision_point event")
    args = parser.parse_args(argv)

    records = load_jsonl(args.recording)
    states = [r for r in records if r.get("t") == "state"]
    sid = states[0]["session_id"] if states else ""
    found = find_session(args.recording, sid)
    mode = json.loads(found[1]).get("mode", "practice") if found else "practice"
    events, decisions, detector = run_detector(states, args.subject, mode)
    slot = detector.subject if detector else "?"
    print(f"{args.recording}: {len(states)} states, {len(events)} tracker events, subject {args.subject} (slot {slot}), "
          f"{len(decisions)} decision points")
    failures = 0
    for ev in decisions:
        errors = [e.message for e in EVENT_V.iter_errors(ev)]
        if errors:
            failures += 1
            print(f"  FAIL {fmt_event(ev)}: {errors[0]}")
    print(f"schema: {len(decisions) - failures}/{len(decisions)} decision points valid")
    print("situations and actions:")
    print_table(situation_table(decisions))
    if args.all:
        for ev in decisions:
            print("  " + fmt_event(ev))
    for ev in decisions[: args.sentences]:
        print(f"  state_text r{ev['round']} f{ev['detail']['start_frame']}: {ev['detail']['state_text']}")
    print("PASS" if failures == 0 else f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
