import argparse
import copy
import json
import sys
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from game.hotloop import fmt_event
from game.recorder import data_dir
from game.state import Tracker

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"
JABS = {"devil_jin": 0x643}
CONNECT_KINDS = ("block", "hit", "counter_hit")


def load_jsonl(path):
    records = []
    lines = Path(path).read_text(encoding="utf-8").splitlines()
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
    for candidate in (path.with_name(f"{path.stem}.session.json"), data_dir() / "sessions" / f"{sid}.json"):
        if candidate.exists():
            return candidate
    return None


def check_session(path):
    schema = json.loads((CONTRACTS / "session.schema.json").read_text())
    meta = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(meta))
    return meta, errors


def event_key(ev):
    return tuple(ev.get(k) for k in ("round", "frame", "kind", "actor", "target", "move_id", "hit_level", "frame_advantage", "damage"))


def replay(states):
    tracker = Tracker(states[0]["session_id"] if states else "")
    events = []
    for s in states:
        events.extend(tracker.step(copy.deepcopy(s)))
    events.extend(tracker.finish())
    return events


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
    session_path = find_session(args.recording, sid)
    if session_path is None:
        print("session: FAIL no session JSON found")
        failures += 1
        meta = {}
    else:
        meta, errors = check_session(session_path)
        for e in errors:
            print(f"session: FAIL {'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}")
        failures += len(errors)
        if not errors:
            print(f"session: ok {session_path} human P{meta['human_slot'] + 1} {meta['human_character']} vs {meta['bot_character']}, rounds {meta['rounds']}")

    replayed = replay(states)
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
            print(f"  r{ev['round']} f{ev['frame']} {who} {ev['kind']} mv 0x{ev['move_id']:04X} {ev.get('hit_level')} adv {ev['frame_advantage']:+d} dmg {ev.get('damage', 0)}{tag}")
    if jab is not None:
        blocked = [ev for ev in events if ev["kind"] == "block" and ev.get("actor") == human and ev.get("move_id") == jab]
        if blocked:
            advs = ", ".join(f"{ev['frame_advantage']:+d}" for ev in blocked)
            print(f"blocked jab 0x{jab:X}: {advs} (tekkendocs: +1)")
        else:
            print(f"blocked jab 0x{jab:X}: none found in this recording")
    print("PASS" if failures == 0 else f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
