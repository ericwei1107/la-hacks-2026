import argparse
import math
import random
import sys
import time
from collections import Counter
from pathlib import Path

from game.combocapture import (BUTTONS, attack_starts, dump_route, fmt_events, input_events, make_row, move_changes, move_names,
                               states)
from game import combotest
from game.combos import CAPTURED_DIR, COUNTER_HIT_REACTIONS, load_captured
from game.difficulty import Difficulty
from game.hotloop import frames
from game.pacer import Pacer
from game.notation import Timing
from game.pad import KillSwitch, connect_pad, load_config
from game.sequencer import Sequencer
from game.reader import DEFAULT_OFFSETS, Reader
from game.readout import run_gate

MAX_LOOP_FRAMES = 1800
START_SLACK = 5
MIN_PRESS = 2
TRACE_BEFORE = 40
TRACE_AFTER = 70
VOTED = ("move_id", "frame_in_move", "dir", "hit_level", "free", "side", "target_move", "target_basic_state",
         "target_status", "target_health", "target_reaction", "distance", "heat")


def loops(gs_iter, slot, log=print):
    rows = []
    complete = False
    prev = None
    for gs in gs_iter:
        if prev is not None and gs["frame"] < prev["frame"]:
            if complete and rows:
                yield rows
            elif rows:
                log(f"  skipped a partial loop ({len(rows)} frames, joined mid-demo)")
            rows = []
            complete = gs["frame"] <= START_SLACK
        elif prev is None:
            complete = gs["frame"] <= START_SLACK
        row = make_row(gs, slot)
        row["distance"] = round(math.hypot(row["target_x"] - gs["players"][slot]["x"], row["target_z"] - gs["players"][slot]["z"]))
        row["heat"] = bool(gs["players"][slot].get("heat_active"))
        rows.append(row)
        if len(rows) > MAX_LOOP_FRAMES:
            log(f"  no reset after {MAX_LOOP_FRAMES} frames; using what was recorded")
            yield rows
            rows = []
            complete = False
        prev = gs


def health_hits(rows):
    hits = []
    for a, b in zip(rows, rows[1:]):
        drop = a["target_health"] - b["target_health"]
        if drop > 0:
            hits.append((b, drop))
    return hits


def widen(events, frames=MIN_PRESS):
    out = []
    for i, (offset, direction, buttons, hold) in enumerate(events):
        if buttons:
            later = [e[0] for e in events[i + 1:] if set(e[2]) & set(buttons)]
            room = later[0] - offset - 1 if later else frames
            hold = max(hold, min(frames, max(1, room)))
        out.append([offset, direction, buttons, hold])
    return out


def opener_events(rows):
    pre = [r for r in rows if r["offset"] <= 0]
    if not pre:
        return []
    base = pre[0]["offset"]
    shifted = [dict(r, offset=r["offset"] - base + 1) for r in pre]
    return [[o + base - 1, d, b, h] for o, d, b, h in input_events(shifted)]


def build_demo_route(name, rows, slot, names=None):
    names = names or {}
    hits = health_hits(rows)
    if not hits:
        return None
    connect = hits[0][0]["frame"]
    for row in rows:
        row["offset"] = row["frame"] - connect
    opener = widen(opener_events(rows))
    if not opener:
        return None
    start = next(r for r in rows if r["offset"] == opener[0][0])
    connect_row = next(r for r in rows if r["offset"] == 0)
    last_hit = hits[-1][0]["offset"]
    combo_rows = [r for r in rows if r["offset"] <= last_hit]
    events = [e for e in widen(input_events(combo_rows)) if e[0] <= last_hit]
    attacks = attack_starts(combo_rows)
    opener_move = next((r["move_id"] for r in rows if r["offset"] >= opener[0][0] and r["hit_level"] != "none"),
                       connect_row["move_id"])
    launcher = names.get(opener_move) or f"0x{opener_move:04X}"
    hit_list = [[h["offset"], d, f"0x{h['move_id']:04X}"] for h, d in hits]
    damage = sum(d for _, d in hits)
    return {
        "captured": True,
        "name": name,
        "guide": f"demo {name}: opener {launcher} then {len(events)} inputs, {len(hit_list)} hits, {damage} damage "
                 f"(from the move-list demo's input fields)",
        "source": "demo",
        "launcher": launcher,
        "launcher_move_id": f"0x{opener_move:04X}",
        "launcher_inputs_replay": True,
        "subject_slot": slot,
        "captured_at": time.strftime("%Y-%m-%dT%H-%M-%S"),
        "input_latency_frames": 2,
        "counter_hit": connect_row["target_reaction"] in COUNTER_HIT_REACTIONS,
        "trigger": "ki_charge" if connect_row["target_reaction"] in COUNTER_HIT_REACTIONS else "round_frame",
        "heat": bool(start.get("heat")),
        "start_round_frame": start["frame"],
        "start_distance": start["distance"],
        "connect_distance": connect_row["distance"],
        "inputs": events,
        "launcher_inputs": opener,
        "attacks": attacks,
        "attack_names": [names.get(int(m, 16)) for _, m in attacks],
        "moves": move_changes([r for r in rows if r["offset"] >= opener[0][0]]),
        "hits": hit_list,
        "damage": damage,
        "notes": [],
        "frames": [r for r in rows if opener[0][0] <= r["offset"] <= last_hit + 30],
    }


def signature(route):
    return route["launcher_move_id"], tuple(a[1] for a in route["attacks"]), tuple(h[1] for h in route["hits"])


def vote(values):
    return Counter(values).most_common(1)[0][0]


def consensus(loop_rows):
    by_frame = [{r["frame"]: r for r in rows} for rows in loop_rows]
    lo = min(min(d) for d in by_frame)
    hi = max(max(d) for d in by_frame)
    out = []
    prev = None
    for t in range(lo, hi + 1):
        seen = [d[t] for d in by_frame if t in d]
        if not seen:
            if prev is not None:
                out.append(dict(prev, frame=t, pressed=[]))
            continue
        row = dict(seen[0], frame=t)
        for key in VOTED:
            row[key] = vote(r.get(key) for r in seen)
        for key in ("pressed", "held"):
            row[key] = [b for b in BUTTONS if 2 * sum(b in r[key] for r in seen) >= len(seen)]
        out.append(row)
        prev = row
    return out


def describe(route, log=print):
    log(f"  opener {route['launcher']} ({route['launcher_move_id']}) from {route['start_distance']} distance, "
        f"{len(route['hits'])} hits, {route['damage']} damage{', starts in heat' if route.get('heat') else ''}")
    log("  opener inputs: " + fmt_events(route["launcher_inputs"]))
    log("  combo inputs:  " + fmt_events(route["inputs"]))
    log("  attacks: " + " ".join(f"{m}{'=' + n if n else ''}@+{o}" for (o, m), n in zip(route["attacks"], route["attack_names"])))
    log("  hits: " + " ".join(f"+{o}:{d}" for o, d, _ in route["hits"]))


def capture(reader, args, log=print):
    gs_iter = states(frames(reader, Pacer(240)), "democapture")
    first = next(gs_iter)
    subject = first["players"][args.slot]
    names = move_names(subject["character"])
    log(f"watching P{args.slot + 1} {subject['character']} for full demo loops (each loop ends when the round counter "
        f"resets). Start the move-list or combo demo; it votes over {args.loops} loops of the same combo.", flush=True)
    groups = {}
    for n, rows in enumerate(loops(gs_iter, args.slot, lambda m: log(m, flush=True)), 1):
        route = build_demo_route(args.name, [dict(r) for r in rows], args.slot, names)
        if route is None:
            log(f"loop {n}: {len(rows)} frames, no hit or no input from P{args.slot + 1}; skipped", flush=True)
            continue
        group = groups.setdefault(signature(route), [])
        group.append(rows)
        log(f"loop {n}: {len(rows)} frames, opener {route['launcher']}, {len(route['hits'])} hits, {route['damage']} damage, "
            f"attacks {' '.join(a[1] for a in route['attacks'])}; {len(group)}/{args.loops} loops of this combo", flush=True)
        if len(group) < args.loops:
            continue
        route = build_demo_route(args.name, consensus(group), args.slot, names)
        route["notes"].append(f"per-frame majority vote over {len(group)} demo loops")
        log(f"consensus over {len(group)} loops:", flush=True)
        describe(route, lambda m: log(m, flush=True))
        out_dir = Path(args.dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{args.name}.json"
        path.write_text(dump_route(route), encoding="utf-8")
        log(f"  saved {path}", flush=True)
        return 0
    return 1


def replay_route(route, counter_hit=False, heat=False):
    route = dict(route)
    if counter_hit or route.get("counter_hit"):
        route["counter_hit"] = True
        route["trigger"] = "ki_charge"
    if heat:
        route["heat"] = True
    return route


def replay_demo(reader, args):
    route = replay_route(load_captured(args.name, args.dir), args.counter_hit, args.heat)
    print(f"{route['guide']}; the demo opener started at round frame {route.get('start_round_frame', 0)} from "
          f"{route['start_distance']} distance", flush=True)
    if args.wait_reset:
        print("NOTHING STARTS UNTIL YOU RESET: press the practice position reset to start attempt 1, and reset again "
              "after every attempt (use --no-wait-reset to start without resets)", flush=True)
    if route.get("trigger") == "ki_charge":
        print("COUNTER HIT ROUTE: after each reset, stand still for half a second, then Ki charge (press 1+2+3+4 "
              "together); Kazuya walks in until df+2 will connect at the demo's distance "
              f"({route.get('connect_distance')}), then fires", flush=True)
    else:
        print(f"the opener waits for the same round frame as the demo, then Kazuya walks in until it will connect at "
              f"the demo's distance ({route.get('connect_distance')})", flush=True)
    if route.get("heat"):
        print("HEAT ROUTE: after each reset Kazuya heat bursts (2+3) first, waits for the burst to finish, then walks in; "
              "leave practice heat settings so the gauge refills on reset", flush=True)
    pad = connect_pad()
    try:
        if args.trace:
            return traced_run(reader, pad, route, args)
        return combotest.run(reader, pad, route, args.name, args.attempts, Difficulty.preset(args.difficulty),
                             args.wait_reset)
    finally:
        pad.release_all()


def fmt_pad(mask):
    if mask is None:
        return "-"
    return mask[0] + ("+" + "+".join(mask[1]) if mask[1] else "")


def compare(runner, route, after=TRACE_AFTER, log=print):
    connect = runner.connect_frame
    if connect is None:
        log("  trace: the opener never connected", flush=True)
        return
    demo = {r["offset"]: r for r in route["frames"]}
    log("  offset | replay: pad bot_move free target_move distance reaction | demo: input bot_move free target_move "
        "distance reaction", flush=True)
    for r in runner.trace or []:
        off = r["frame"] - connect
        if not -TRACE_BEFORE <= off <= after:
            continue
        d = demo.get(off)
        demo_text = "-" if d is None else (
            f"{d['dir']}{'+' + '+'.join(d['pressed']) if d['pressed'] else ''} 0x{d['move_id']:04X} {int(d['free'])} "
            f"0x{d['target_move']:04X} {d['distance']:>5} {d['target_reaction']}")
        log(f"  {off:+4d} | {fmt_pad(r.get('pad')):>6} 0x{r['bot_move']:04X} {int(r['bot_free'])} 0x{r['target_move']:04X} "
            f"{r['distance']:>5} {r['reaction']:>2} | {demo_text}", flush=True)


def traced_run(reader, pad, route, args):
    config = load_config()
    difficulty = Difficulty.preset(args.difficulty)
    seq = Sequencer(pad, config["input_latency_frames"], difficulty, random.Random(),
                    Timing.from_config(config.get("timing")))
    gs_iter = combotest.states(frames(reader, Pacer(), pad.check_kill))
    bot = 1 - next(gs_iter)["human_slot"]
    traced = 0
    done = 0
    for i in range(1, args.attempts + 1):
        gs = combotest.wait_settled(gs_iter, bot, args.wait_reset)
        runner = combotest.attempt(gs_iter, seq, route, args.name, bot, difficulty, gs, trace=True)
        combotest.report(i, args.attempts, runner)
        if runner.reach is not None:
            print(f"  opener fired from {round(runner.opener_distance)} and connected at "
                  f"{round(runner.opener_distance - runner.reach)} (demo {route['connect_distance']}); "
                  f"next attempt fires from {runner.fire_distance()}", flush=True)
        done += runner.status == "done"
        if runner.status != "done" and traced < args.trace:
            traced += 1
            compare(runner, route)
    print(f"\n{args.name}: completed {done}/{args.attempts}", flush=True)
    return 0


def main(argv=None):
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Capture a combo from the in-game move-list or combo demo and replay it")
    parser.add_argument("--name", required=True, help="route name; saved as game/combos_captured/<name>.json")
    parser.add_argument("--slot", type=int, choices=(0, 1), default=0, help="slot the demo character is in")
    parser.add_argument("--loops", type=int, default=5, help="demo loops of the same combo to vote over before saving")
    parser.add_argument("--replay", action="store_true", help="run the captured route on the practice dummy instead")
    parser.add_argument("--attempts", type=int, default=10)
    parser.add_argument("--difficulty", type=int, default=5, choices=range(1, 6))
    parser.add_argument("--wait-reset", dest="wait_reset", action="store_true", default=True, help=argparse.SUPPRESS)
    parser.add_argument("--no-wait-reset", dest="wait_reset", action="store_false",
                        help="start attempts without waiting for a practice position reset (the opener needs the demo spacing)")
    parser.add_argument("--counter-hit", action="store_true",
                        help="fire the opener when you Ki charge (1+2+3+4) so it counter hits; on by default for routes "
                             "whose demo opener counter hit")
    parser.add_argument("--heat", action="store_true",
                        help="heat burst (2+3) before the opener so the combo runs in heat; on by default for routes "
                             "whose demo started in heat")
    parser.add_argument("--trace", type=int, default=0, metavar="N",
                        help="print the first N failed attempts frame by frame next to the demo")
    parser.add_argument("--dir", default=str(CAPTURED_DIR))
    parser.add_argument("--offsets", default=str(DEFAULT_OFFSETS))
    parser.add_argument("--out", help="also write everything printed to this file")
    args = parser.parse_args(argv)
    if args.out:
        sys.stdout = combotest.Tee(sys.stdout, args.out)
    reader = Reader(args.offsets)
    try:
        if not run_gate(reader, args.offsets):
            return 1
        return replay_demo(reader, args) if args.replay else capture(reader, args)
    except (KeyboardInterrupt, KillSwitch) as e:
        print(f"stopped: {e}" if str(e) else "stopped: Ctrl+C", flush=True)
        return 1
    finally:
        reader.close()


if __name__ == "__main__":
    sys.exit(main())
