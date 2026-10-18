import argparse
import json
import re
import sys
import time
from collections import deque
from pathlib import Path

from game import combotest
from game import state as st
from game.combos import CAPTURED_DIR, connect_signal, last_press, load_captured, load_routes, plan
from game.difficulty import Difficulty
from game.hotloop import frames
from game.notation import Timing, compile_notation, parse_token, runs
from game.pacer import Pacer
from game.pad import KillSwitch, connect_pad
from game.reader import DEFAULT_OFFSETS, Reader
from game.readout import run_gate

ARM_FRAMES = 20
PRE_FRAMES = 45
MAX_FRAMES = 600
SETTLE_FRAMES = 10
BUTTONS = ("1", "2", "3", "4")
DEFAULT_LAUNCHER = "f,n,d,df+2"
DEFAULT_LINKS_ROUTE = "ewgf_full"


def states(it, sid="combocapture"):
    for snap, _ in it:
        gs = st.build_state(snap.players, snap.human_slot, snap.round_frame, sid)
        if gs is not None:
            yield gs


def make_row(gs, slot):
    s, t = gs["players"][slot], gs["players"][1 - slot]
    return {"frame": gs["frame"], "move_id": s["move_id"], "frame_in_move": s["frame_in_move"], "dir": s["dir_held"],
            "pressed": [b for b in s["buttons_pressed"] if b in BUTTONS], "held": [b for b in s["buttons_held"] if b in BUTTONS],
            "side": s["side"], "hit_level": s["hit_level"], "free": s["free_movement"],
            "target_move": t["move_id"], "target_basic_state": t["basic_state"], "target_status": t["status"],
            "target_x": t["x"], "target_y": t["y"], "target_z": t["z"], "target_health": t["health"],
            "target_reaction": t["hit_reaction"]}


def landed(target, connect_frame, frame):
    generic = target["move_id"] & st.GENERIC_MASK == st.GENERIC_BASE
    return frame > connect_frame and generic and not target["status"] & st.JUGGLED_BIT


def wait_connect(gs_iter, slot):
    ring = deque(maxlen=PRE_FRAMES)
    calm = 0
    prev = None
    for gs in gs_iter:
        if prev is not None and gs["frame"] < prev["frame"]:
            ring.clear()
            calm = 0
        ring.append(make_row(gs, slot))
        t = gs["players"][1 - slot]
        if prev is not None and calm >= ARM_FRAMES and connect_signal(prev["players"][1 - slot], t):
            return gs, prev, list(ring)
        calm = calm + 1 if not t["hit_reaction"] and t["free_movement"] else 0
        prev = gs
    return None, None, None


def record(gs_iter, slot):
    gs, prev, rows = wait_connect(gs_iter, slot)
    if gs is None:
        return None
    connect = gs["frame"]
    health = prev["players"][1 - slot]["health"]
    hits = []
    free_run = 0
    last = gs
    while True:
        t = gs["players"][1 - slot]
        if gs is not last:
            if gs["frame"] < last["frame"]:
                return None
            rows.append(make_row(gs, slot))
        if t["health"] < health:
            hits.append([gs["frame"] - connect, health - t["health"], f"0x{gs['players'][slot]['move_id']:04X}"])
        health = t["health"]
        free_run = free_run + 1 if t["free_movement"] and not t["hit_reaction"] else 0
        if landed(t, connect, gs["frame"]) or free_run >= SETTLE_FRAMES or gs["frame"] - connect > MAX_FRAMES:
            break
        last = gs
        gs = next(gs_iter)
    for row in rows:
        row["offset"] = row["frame"] - connect
    return {"connect_frame": connect, "rows": rows, "hits": hits}


def input_events(rows):
    post = [r for r in rows if r["offset"] >= 1]
    events = []
    prev_dir = "n"
    prev_held = set()
    for i, row in enumerate(post):
        pressed = sorted(set(row["pressed"]) | (set(row["held"]) - prev_held))
        if row["dir"] != prev_dir or pressed:
            hold = 0
            if pressed:
                hold = 1
                while i + hold < len(post) and set(pressed) <= set(post[i + hold]["held"]):
                    hold += 1
            events.append([row["offset"], row["dir"], pressed, hold])
        prev_dir = row["dir"]
        prev_held = set(row["held"])
    return events


def attack_starts(rows):
    out = []
    pending = False
    prev = None
    for row in rows:
        if row["offset"] < 1:
            prev = row
            continue
        if prev is not None and row["move_id"] != prev["move_id"]:
            pending = True
        if pending and row["hit_level"] != "none":
            out.append([row["offset"], f"0x{row['move_id']:04X}"])
            pending = False
        prev = row
    return out


def move_changes(rows):
    out = []
    for i, row in enumerate(rows):
        if i == 0 or row["move_id"] != rows[i - 1]["move_id"]:
            out.append([row["offset"], f"0x{row['move_id']:04X}", row["frame_in_move"], row["hit_level"]])
    return out


def attack_groups(notations):
    groups = []
    for text in notations:
        pre = []
        first = True
        for tok in (t.strip() for t in re.split(r"[,:]", text)):
            pre.append(tok)
            if parse_token(tok, ",").has_buttons:
                groups.append((",".join(pre), not first and len(pre) == 1))
                pre = []
                first = False
    return groups


def derive_events(attacks, groups, timing=Timing()):
    events = []
    prev_start = 0
    for (start, _), (group, follow) in zip(attacks, groups):
        frames = compile_notation(group, timing)
        press = (prev_start + start) // 2 if follow and prev_start else start
        anchor = press - last_press(frames)
        i = 0
        for (direction, buttons), n in runs(frames):
            events.append([anchor + i, direction, list(buttons), n if buttons else 0])
            i += n
        prev_start = start
    events.sort(key=lambda e: e[0])
    return [e for e in events if e[0] >= 1]


def move_names(character, path=None):
    path = path or Path(__file__).resolve().parents[1] / "characters" / character / "moves.json"
    if not path.exists():
        return {}
    moves = json.loads(path.read_text(encoding="utf-8"))["moves"]
    return {int(m["move_id"], 16): m["command"].split(" (")[0] for m in moves if m.get("move_id")}


def pre_events(rows):
    shifted = [dict(r, offset=r["offset"] + PRE_FRAMES) for r in rows if r["offset"] <= 0]
    return [[o - PRE_FRAMES, d, b, h] for o, d, b, h in input_events(shifted)]


def build_route(name, take, slot, launcher, links, names=None):
    rows = take["rows"]
    names = names or {}
    connect_move = next(r for r in rows if r["offset"] == 0)["move_id"]
    launcher = launcher or names.get(connect_move) or DEFAULT_LAUNCHER
    events = input_events(rows)
    attacks = attack_starts(rows)
    pressed_after = sum(1 for e in events if e[2])
    source = "inputs"
    notes = []
    if not pressed_after:
        groups = attack_groups(links)[len(attack_groups([launcher])):]
        if len(groups) != len(attacks):
            notes.append(f"{len(attacks)} attack moves after the launcher but {len(groups)} inputs in the links; "
                         f"mapped the first {min(len(groups), len(attacks))}")
        events = derive_events(attacks, groups)
        source = "moves"
    connect_row = next(r for r in rows if r["offset"] == 0)
    hits = take["hits"]
    return {
        "captured": True,
        "name": name,
        "guide": f"captured {name}: {launcher} then {len(events)} inputs, {len(hits)} hits, {sum(h[1] for h in hits)} damage (from {source})",
        "source": source,
        "launcher": launcher,
        "launcher_move_id": f"0x{connect_row['move_id']:04X}",
        "subject_slot": slot,
        "captured_at": time.strftime("%Y-%m-%dT%H-%M-%S"),
        "input_latency_frames": 2,
        "inputs": events,
        "launcher_inputs": pre_events(rows),
        "attacks": attacks,
        "attack_names": [names.get(int(m, 16)) for _, m in attacks],
        "moves": move_changes(rows),
        "hits": hits,
        "damage": sum(h[1] for h in hits),
        "notes": notes,
        "frames": rows,
    }


def dump_route(route):
    parts = []
    for key, value in route.items():
        if isinstance(value, list) and value and isinstance(value[0], (list, dict)):
            body = "[\n  " + ",\n  ".join(json.dumps(v) for v in value) + "\n ]"
        else:
            body = json.dumps(value)
        parts.append(f" {json.dumps(key)}: {body}")
    return "{\n" + ",\n".join(parts) + "\n}\n"


def fmt_events(events):
    return " ".join(f"{o:+d}:{d}{'+' + '+'.join(b) if b else ''}{'x' + str(h) if h > 1 else ''}" for o, d, b, h in events) or "-"


def describe_take(route):
    filled = route["source"] == "inputs"
    print(f"  input fields: {'filled' if filled else 'empty (only move ids changed); input frames derived from move start frames'}",
          flush=True)
    print(f"  launcher {route['launcher']} ({route['launcher_move_id']}), {len(route['hits'])} hits, {route['damage']} damage",
          flush=True)
    print("  attacks after the launcher: " + " ".join(
        f"{m}{'=' + n if n else ''}@+{o}" for (o, m), n in zip(route["attacks"], route["attack_names"])), flush=True)
    print("  launcher inputs: " + fmt_events(route["launcher_inputs"]), flush=True)
    print("  inputs: " + fmt_events(route["inputs"]), flush=True)
    for note in route["notes"]:
        print(f"  note: {note}", flush=True)


def capture(reader, args, links):
    gs_iter = states(frames(reader, Pacer()))
    first = next(gs_iter)
    subject = first["players"][args.slot]
    print(f"capturing P{args.slot + 1} {subject['character']} (human is P{first['human_slot'] + 1}); target is "
          f"P{2 - args.slot} {first['players'][1 - args.slot]['character']}. Perform the combo; a take starts when a hit "
          f"lands after the target has been idle for {ARM_FRAMES} frames and ends when the target lands.", flush=True)
    names = move_names(subject["character"])
    out_dir = Path(args.dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    kept = 0
    take_no = 0
    while kept < args.takes:
        take = record(gs_iter, args.slot)
        if take is None:
            print("take interrupted by a round counter reset; waiting for the next one", flush=True)
            continue
        take_no += 1
        route = build_route(args.name, take, args.slot, args.launcher, links, names)
        print(f"take {take_no}:", flush=True)
        describe_take(route)
        if args.hits and len(route["hits"]) != args.hits:
            print(f"  discarded: target took {len(route['hits'])} hits, want {args.hits}", flush=True)
            continue
        kept += 1
        path = out_dir / f"{args.name}.json"
        path.write_text(dump_route(route), encoding="utf-8")
        print(f"  saved {path}", flush=True)
    return 0


def replay(reader, args):
    route = load_captured(args.name, args.dir)
    pad = connect_pad()
    try:
        return combotest.run(reader, pad, route, args.name, args.attempts, Difficulty.preset(args.difficulty), args.wait_reset)
    finally:
        pad.release_all()


def main(argv=None):
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Capture a combo from live play (or a demo) and replay it on the bot")
    parser.add_argument("--name", required=True, help="route name; saved as game/combos_captured/<name>.json")
    parser.add_argument("--slot", type=int, choices=(0, 1), default=0, help="slot performing the combo while capturing")
    parser.add_argument("--hits", type=int, help="keep only takes where the target took exactly this many hits")
    parser.add_argument("--takes", type=int, default=1, help="stop after this many kept takes (the last one is saved)")
    parser.add_argument("--launcher", help="notation the bot uses for the launcher on replay (default: looked up from the "
                                           f"launcher's move id in characters/<character>/moves.json, else {DEFAULT_LAUNCHER})")
    parser.add_argument("--links", help="the combo's links separated by ';', used only when the input fields stay empty "
                                        f"(default: the links of {DEFAULT_LINKS_ROUTE})")
    parser.add_argument("--replay", action="store_true", help="run the captured route on the practice dummy instead")
    parser.add_argument("--attempts", type=int, default=10)
    parser.add_argument("--difficulty", type=int, default=5, choices=range(1, 6))
    parser.add_argument("--wait-reset", action="store_true")
    parser.add_argument("--dir", default=str(CAPTURED_DIR))
    parser.add_argument("--offsets", default=str(DEFAULT_OFFSETS))
    args = parser.parse_args(argv)
    links = args.links.split(";") if args.links else [l.notation for l in plan(load_routes()["routes"][DEFAULT_LINKS_ROUTE])]

    reader = Reader(args.offsets)
    try:
        if not run_gate(reader, args.offsets):
            return 1
        return replay(reader, args) if args.replay else capture(reader, args, links)
    except (KeyboardInterrupt, KillSwitch) as e:
        print(f"stopped: {e}" if str(e) else "stopped: Ctrl+C", flush=True)
        return 1
    finally:
        reader.close()


if __name__ == "__main__":
    sys.exit(main())
