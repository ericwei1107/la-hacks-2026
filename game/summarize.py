import argparse
import copy
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from game.hotloop import fmt_event, fmt_record
from game.recorder import data_dir
from game.state import Tracker

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"
JABS = {"devil_jin": 0x643}
CONNECT_KINDS = ("block", "hit", "counter_hit")
OUTCOME_WINDOW = 60
BREAK_WINDOW = 60


def zip_members(path):
    with zipfile.ZipFile(path) as z:
        return {name: z.read(name).decode("utf-8") for name in z.namelist()}


def recording_text(path):
    if str(path).endswith(".zip"):
        members = zip_members(path)
        return next(text for name, text in members.items() if name.endswith(".jsonl"))
    return Path(path).read_text(encoding="utf-8")


def load_jsonl(path):
    records = []
    lines = recording_text(path).splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            if i != len(lines) - 1:
                raise
    return records


def find_session(path, sid):
    path = Path(path)
    if path.suffix == ".zip":
        for name, text in zip_members(path).items():
            if name.endswith(".session.json"):
                return f"{path.as_posix()}:{name}", text
    for candidate in (path.with_name(f"{path.stem}.session.json"), data_dir() / "sessions" / f"{sid}.json"):
        if candidate.exists():
            return str(candidate), candidate.read_text(encoding="utf-8")
    return None


def check_session(text):
    schema = json.loads((CONTRACTS / "session.schema.json").read_text())
    meta = json.loads(text)
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(meta))
    return meta, errors


def event_key(ev):
    detail = ev.get("detail") or {}
    keys = ("round", "frame", "kind", "actor", "target", "move_id", "hit_level", "frame_advantage", "damage")
    return tuple(ev.get(k) for k in keys) + (detail.get("reason"), detail.get("winner"))


def replay(states, mode="practice", rounds_to_win=3):
    versus = mode == "versus"
    tracker = Tracker(states[0]["session_id"] if states else "", timeouts=versus, rounds_to_win=rounds_to_win if versus else None)
    events = []
    for s in states:
        if tracker.match_over and tracker.prev is not None and s["frame"] < tracker.prev["frame"]:
            break
        events.extend(tracker.step(copy.deepcopy(s)))
    events.extend(tracker.finish())
    return events


def first_event(events, frame, rnd, window, test):
    for ev in events:
        if ev["round"] == rnd and frame <= ev["frame"] <= frame + window and test(ev):
            return ev
    return None


def outcome(rec, events, bot):
    kind = rec["reflex"]["kind"]
    rnd = rec["round"]
    if kind == "block":
        ev = first_event(events, rec["frame_asked"], rnd, OUTCOME_WINDOW,
                         lambda e: e.get("target") == bot and e["kind"] in CONNECT_KINDS + ("throw",))
        return ev["kind"] if ev else "no contact"
    if kind == "punish":
        if rec["chosen"] == "none":
            return "not attempted"
        ev = first_event(events, rec["frame"], rnd, OUTCOME_WINDOW,
                         lambda e: e.get("actor") == bot and e["kind"] in CONNECT_KINDS + ("whiff",))
        return f"{ev['kind']} mv 0x{ev['move_id']:04X}" if ev else "no result"
    if kind == "wakeup":
        ev = first_event(events, rec["frame"], rnd, OUTCOME_WINDOW,
                         lambda e: e.get("target") == bot and e["kind"] in CONNECT_KINDS + ("throw",))
        if ev is None:
            return "clean getup"
        return f"{ev['kind']} by mv 0x{ev['move_id']:04X} +{ev['frame'] - rec['frame']}"
    if kind == "throw_break":
        ev = first_event(events, rec["frame"], rnd, BREAK_WINDOW, lambda e: e["kind"] == "throw_break" and e.get("actor") == bot)
        return "broke" if ev else "thrown"
    return ""


def reflex_section(records, events, human):
    decisions = [r for r in records if r.get("t") == "tactical" and r.get("source") == "reflex"]
    if not decisions:
        print("reflex decisions: none")
        return
    bot = 1 - human
    print("reflex decisions (=> what happened next):")
    totals = {}
    for rec in decisions:
        result = outcome(rec, events, bot)
        print(f"  {fmt_record(rec)}  => {result}")
        kind = rec["reflex"]["kind"]
        key = "rolled miss" if rec["reflex"].get("rolled_miss") else result.split(" ")[0]
        totals.setdefault(kind, Counter())[key] += 1
    for kind, counts in sorted(totals.items()):
        print(f"  {kind}: {sum(counts.values())} decisions, " + ", ".join(f"{k} {n}" for k, n in counts.most_common()))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize a Kumite recording: session check, events, frame advantage")
    parser.add_argument("recording")
    args = parser.parse_args(argv)

    records = load_jsonl(args.recording)
    states = [r for r in records if r.get("t") == "state"]
    events = [r for r in records if r.get("t") == "event"]
    sid = records[0]["session_id"] if records else ""
    print(f"{args.recording}: {len(states)} states, {len(events)} events, rounds {sorted({r['round'] for r in records})}")

    failures = 0
    found = find_session(args.recording, sid)
    if found is None:
        print("session: FAIL no session JSON found")
        failures += 1
        meta = {}
    else:
        session_path, session_text = found
        meta, errors = check_session(session_text)
        for e in errors:
            print(f"session: FAIL {'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}")
        failures += len(errors)
        if not errors:
            print(f"session: ok {session_path} human P{meta['human_slot'] + 1} {meta['human_character']} vs {meta['bot_character']}, rounds {meta['rounds']}")

    replayed = replay(states, meta.get("mode", "practice"))
    recorded_keys = Counter(event_key(e) for e in events)
    replayed_keys = Counter(event_key(e) for e in replayed)
    if recorded_keys == replayed_keys:
        print(f"replay: ok, re-running the tracker on the states reproduces all {len(replayed)} events")
    else:
        print("replay: MISMATCH between recorded events and the current tracker")
        for key in sorted((recorded_keys - replayed_keys).elements(), key=str):
            print(f"  only recorded: {key}")
        for key in sorted((replayed_keys - recorded_keys).elements(), key=str):
            print(f"  only replayed: {key}")
        failures += 1

    print("events:")
    for ev in events:
        print("  " + fmt_event(ev))

    human = meta.get("human_slot", states[0]["human_slot"] if states else 0)
    human_char = meta.get("human_character")
    jab = JABS.get(human_char)
    print("frame advantage on connection (attacker's perspective):")
    for ev in events:
        if ev["kind"] in CONNECT_KINDS:
            who = "human" if ev.get("actor") == human else "bot"
            tag = "  <- jab (1)" if jab is not None and ev.get("actor") == human and ev.get("move_id") == jab else ""
            print(f"  r{ev['round']} f{ev['frame']} {who} {ev['kind']} mv 0x{ev['move_id']:04X} {ev.get('hit_level')} adv {'string' if ev['frame_advantage'] is None else format(ev['frame_advantage'], '+d')} dmg {ev.get('damage', 0)}{tag}")
    if jab is not None:
        blocked = [ev for ev in events if ev["kind"] == "block" and ev.get("actor") == human and ev.get("move_id") == jab]
        if blocked:
            advs = ", ".join("string" if ev["frame_advantage"] is None else f"{ev['frame_advantage']:+d}" for ev in blocked)
            print(f"blocked jab 0x{jab:X}: {advs} (tekkendocs: +1)")
        else:
            print(f"blocked jab 0x{jab:X}: none found in this recording")
    reflex_section(records, replayed, human)
    print("PASS" if failures == 0 else f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
