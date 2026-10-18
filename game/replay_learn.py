import argparse
import copy
import json
import random
import sys
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from game.detect import Detector
from game.difficulty import Difficulty
from game.hotloop import fmt_event
from game.learning import Learning
from game.notation import Timing
from game.options import CLASSES, load_options
from game.pad import load_config
from game.recorder import data_dir
from game.reflex import Reflex, load_punishers, load_wakeups
from game.replay_reflex import RecordingPad
from game.sequencer import Sequencer
from game.state import Tracker
from game.summarize import CONTRACTS, find_session, load_jsonl
from game.tactical import LAYA_WEIGHT, Tactical

REPLAY_DIR = "replay"


def default_data():
    return data_dir() / REPLAY_DIR


def schema(name, sub=None):
    data = json.loads((CONTRACTS / f"{name}.schema.json").read_text())
    if sub:
        data = {**data["$defs"][sub], "$defs": data["$defs"]}
    return Draft202012Validator(data, format_checker=FormatChecker())


EVENT_V = schema("event")
SUMMARY_V = schema("round_summary")
ROUND_V = schema("metrics", "round")
PROFILE_V = schema("profile")
PLAN_V = schema("gameplan")


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


class Run:
    def __init__(self):
        self.events = []
        self.decisions = []
        self.records = []
        self.summaries = []
        self.boosts = []
        self.learning = None
        self.detector = None
        self.tactical = None
        self.last_state = None


def run_learning(states, player="replay", difficulty=3, mode="practice", rounds_to_win=3, root=None, seed=0,
                 tactical=False, predictor=True, config=None, fresh=True, laya=None, laya_weight=LAYA_WEIGHT):
    versus = mode == "versus"
    sid = states[0]["session_id"] if states else ""
    root = Path(root) if root is not None else default_data()
    if fresh and sid:
        (root / "learning" / f"{sid}.jsonl").unlink(missing_ok=True)
    tracker = Tracker(sid, timeouts=versus, rounds_to_win=rounds_to_win if versus else None)
    diff = Difficulty.preset(difficulty)
    rng = random.Random(seed)
    run = Run()
    seq = reflex = None
    for raw in states:
        if tracker.match_over and tracker.prev is not None and raw["frame"] < tracker.prev["frame"]:
            break
        state = copy.deepcopy(raw)
        evs = tracker.step(state)
        human = state["human_slot"]
        if run.learning is None:
            bot_char = state["players"][1 - human]["character"]
            options = load_options(bot_char)[0]
            run.detector = Detector(human, options)
            run.learning = Learning(player, state["players"][human]["character"], options, diff, rng, root, predictor=predictor, fresh=fresh)
            if tactical:
                config = config or load_config()
                latency = config["input_latency_frames"]
                seq = Sequencer(RecordingPad(config), latency, diff, rng, Timing.from_config(config.get("timing")))
                reflex = Reflex(seq, diff, latency, load_punishers(bot_char)[0], rng, load_wakeups(bot_char)[0])
                run.tactical = Tactical(seq, diff, latency, options, rng, learning=run.learning, laya=laya, laya_weight=laya_weight,
                                        recent=lambda: run.detector.recent)
        found = run.detector.step(state, evs)
        learned = run.learning.step(state, evs + found)
        run.records += learned
        if run.tactical is not None:
            run.records += reflex.step(state, evs)
            run.records += run.tactical.step(state, evs, reflex)
            seq.on_frame(state["frame"], state["players"][1 - human], reflex.live(state))
            seq.pop_finished()
        collect_summaries(run, learned, state)
        run.events += evs
        run.decisions += found
        run.last_state = state
    final = tracker.finish()
    if final and run.last_state is not None:
        learned = run.learning.step(run.last_state, final)
        run.records += learned
        collect_summaries(run, learned, run.last_state)
    run.events += final
    return run


def collect_summaries(run, learned, state):
    for rec in learned:
        if rec.get("t") == "round_summary":
            probe = copy.deepcopy(state)
            probe["round"] = rec["round"] + 1
            probe["derived"]["situation"] = "neutral"
            run.summaries.append(rec)
            run.boosts.append((rec["round"], run.learning.boosts(probe)))


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


def fmt_boosts(boosts):
    if not boosts:
        return "none"
    return ", ".join(f"{cls} x{b['factor']} ({b['situation']} {b['action']} p={b['p']} n={b['n']}{' retest' if b['retest'] else ''})"
                     for cls, b in sorted(boosts.items()))


def print_learning(run):
    learning = run.learning
    print("learning per round:")
    for rec in learning.rounds:
        acc = "n/a" if rec["prediction_accuracy"] is None else f"{rec['prediction_accuracy']:.0%}"
        print(f"  round {rec['round']}: prediction accuracy {acc}" + (", player changed" if rec["player_changed"] else ""))
        for key, row in rec["habits"].items():
            print(f"    {key:<24} {row['action']:<11} p={row['p']:.2f} n={row['n']:<3} mastery={row['mastery']:.2f}"
                  + ("  fixed" if row["fixed"] else ""))
        for key, arms in rec["bandit"].items():
            print(f"    bandit {key}: " + ", ".join(f"{arm} {rate:.2f}" for arm, rate in arms.items()))
    for rnd, boosts in run.boosts:
        print(f"  boosts after round {rnd}: {fmt_boosts(boosts)}")
    for rec in run.records:
        if rec.get("t") == "learning_event":
            print(f"  r{rec['round']} f{rec['frame']} learning_event {rec['event']} {rec.get('situation', '')}")
    for s in run.summaries:
        habits = "; ".join(f"{h['situation']} {h['action']} p={h['p']:.2f} n={h['n']}" for h in s["top_habits"])
        print(f"  round_summary r{s['round']}: winner {s['winner']}, human took {s['human_damage_taken']}, bot took {s['bot_damage_taken']}, "
              f"exploited {s['exploited']}, fixed {s['newly_fixed']}, regressed {s['regressed']}; top: {habits}")
    print(f"  profile {learning.profile_path} (session {learning.sessions}), learning file {learning.learning_path}")


def validate_run(run):
    failures = 0
    for ev in run.decisions:
        failures += len(list(EVENT_V.iter_errors(ev)))
    for s in run.summaries:
        for e in SUMMARY_V.iter_errors(s):
            failures += 1
            print(f"  FAIL round_summary r{s['round']}: {e.message}")
    for rec in run.learning.rounds:
        for e in ROUND_V.iter_errors(rec):
            failures += 1
            print(f"  FAIL learning_round r{rec['round']}: {e.message}")
    for e in PROFILE_V.iter_errors(run.learning.profile()):
        failures += 1
        print(f"  FAIL profile: {e.message}")
    for rec in run.records:
        if rec.get("t") == "plan":
            body = {k: v for k, v in rec.items() if k not in ("t", "round", "frame", "session_id")}
            for e in PLAN_V.iter_errors(body):
                failures += 1
                print(f"  FAIL plan: {e.message}")
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description="Replay a recording through the tracker, the situation detector and the learners (no game needed)")
    parser.add_argument("recording")
    parser.add_argument("--subject", default="human", choices=("human", "bot"), help="whose responses to detect (bot = mirror check)")
    parser.add_argument("--sentences", type=int, default=3, help="how many state_text samples to print")
    parser.add_argument("--all", action="store_true", help="print every decision_point event")
    parser.add_argument("--player", default="replay", help="profile name under <data-dir>/profiles")
    parser.add_argument("--difficulty", type=int, default=3, choices=range(1, 6))
    parser.add_argument("--data-dir", help="where profiles/ and learning/ are written (default DATA_DIR/replay)")
    parser.add_argument("--keep-profile", action="store_true", help="continue from the profile and predictor a previous replay left in --data-dir")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--tactical", action="store_true", help="also dry-run the tactical layer with the learners (shows habit-driven picks)")
    parser.add_argument("--no-predictor", action="store_true")
    parser.add_argument("--laya", action="store_true", help="with --tactical: Laya (DATA_DIR/models/laya-ft when present) answers every tactical decision, synchronously")
    parser.add_argument("--laya-weight", type=float, default=LAYA_WEIGHT)
    args = parser.parse_args(argv)
    oracle = None
    if args.laya:
        from game.laya import Laya, Oracle, current_version, resolve_model
        model, kind = resolve_model()
        print(f"laya: {kind} weights from {model}")
        oracle = Oracle(Laya(model).load(), current_version() if kind == "fine-tuned" else None, threaded=False)

    records = load_jsonl(args.recording)
    states = [r for r in records if r.get("t") == "state"]
    sid = states[0]["session_id"] if states else ""
    found = find_session(args.recording, sid)
    mode = json.loads(found[1]).get("mode", "practice") if found else "practice"
    failures = 0
    if args.subject == "bot":
        events, decisions, detector = run_detector(states, args.subject, mode)
        print(f"{args.recording}: {len(states)} states, {len(events)} tracker events, subject bot (slot {detector.subject if detector else '?'}), "
              f"{len(decisions)} decision points")
        run = None
    else:
        run = run_learning(states, args.player, args.difficulty, mode, root=args.data_dir, seed=args.seed, tactical=args.tactical,
                           predictor=not args.no_predictor, fresh=not args.keep_profile, laya=oracle, laya_weight=args.laya_weight)
        events, decisions = run.events, run.decisions
        slot = run.detector.subject if run.detector else "?"
        if run.learning is None:
            run = None
        print(f"{args.recording}: {len(states)} states, {len(events)} tracker events, subject human (slot {slot}), "
              f"{len(decisions)} decision points")
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
    if run is not None:
        print_learning(run)
        if args.tactical:
            picks = [r for r in run.records if r.get("t") == "tactical" and r.get("source") in ("default", "habit", "laya")]
            sources = Counter(r["source"] for r in picks)
            by_source = {s: Counter(r["chosen"] for r in picks if r["source"] == s) for s in sources}
            print(f"tactical dry run: {len(picks)} decisions (" + ", ".join(f"{s} {n}" for s, n in sources.most_common()) + ")")
            for s, mix in by_source.items():
                print(f"  {s}: " + ", ".join(f"{k} {n}" for k, n in mix.most_common()))
            habit_moves = Counter((r["tactical"].get("move"), r["chosen"]) for r in picks if r["source"] == "habit")
            if habit_moves:
                print("  habit picks: " + ", ".join(f"{m} ({c}) {n}" for (m, c), n in habit_moves.most_common(8)))
            if oracle is not None:
                changed = sum(1 for r in picks if (r["tactical"].get("laya") or {}).get("changed"))
                print(f"  laya: {sources['laya']}/{len(picks)} decisions answered, {changed} changed the habit target (weight {args.laya_weight})")
            for rec in run.records:
                if rec.get("t") == "plan":
                    print(f"  plan r{rec['round']} f{rec['frame']}: {rec['note']!r} targets {rec['target_habits']}")
        failures += validate_run(run)
        print(f"schema: round_summary {len(run.summaries)}, learning_round {len(run.learning.rounds)}, profile checked")
    print("PASS" if failures == 0 else f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
