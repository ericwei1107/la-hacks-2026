import argparse
import copy
import itertools
import random
import sys

from game import state as st
from game.combos import ComboRunner, load_routes
from game.difficulty import Difficulty
from game.hotloop import frames
from game.notation import Timing
from game.pacer import Pacer
from game.pad import KillSwitch, connect_pad, load_config
from game.reader import DEFAULT_OFFSETS, Reader
from game.readout import run_gate
from game.sequencer import Sequencer

ATTEMPTS = 10
SWEEP_ATTEMPTS = 5
SETTLE_FRAMES = 30
TIMEOUT_FRAMES = 900
GETUP_NAG_FRAMES = 120
COUNTER_CODES = {code for code, name in st.REACTIONS.items() if name == "counter_hit"}
INT_KEYS = ("delay", "hold")


def states(it, sid="combotest"):
    for snap, _ in it:
        gs = st.build_state(snap.players, snap.human_slot, snap.round_frame, sid)
        if gs is not None:
            yield gs


def calm(gs, bot):
    target = gs["players"][1 - bot]
    return (all(p["free_movement"] for p in gs["players"]) and not target["status"] & st.DOWNED_BIT
            and not target["status"] & st.JUGGLED_BIT)


def wait_settled(gs_iter, bot, wait_reset):
    run = 0
    last = None
    reset = not wait_reset
    down = 0
    for gs in gs_iter:
        if last is not None and gs["frame"] < last:
            reset = True
            run = 0
        last = gs["frame"]
        down = down + 1 if gs["players"][1 - bot]["status"] & st.DOWNED_BIT else 0
        if down == GETUP_NAG_FRAMES:
            print("  waiting: you are on the floor; tap up to stand so the next attempt can start", flush=True)
        run = run + 1 if calm(gs, bot) else 0
        if reset and run >= SETTLE_FRAMES:
            return gs
    return None


def attempt(gs_iter, seq, route, name, bot, difficulty, first, trace=False):
    runner = ComboRunner(route, seq, bot, difficulty, name=name, trace=trace)
    start = first["frame"]
    gs = first
    while True:
        runner.on_state(gs)
        mask = seq.on_frame(gs["frame"], gs["players"][bot])
        if runner.trace:
            runner.trace[-1]["pad"] = mask
        if runner.finished:
            break
        if gs["frame"] - start > TIMEOUT_FRAMES:
            runner.stop(gs["frame"], reason=f"no result after {TIMEOUT_FRAMES} frames")
            break
        gs = next(gs_iter)
    seq.cancel(gs["frame"])
    seq.pop_finished()
    return runner


def fmt_ids(hits):
    return " ".join(f"0x{h['move_id']:04X}" for h in hits)


def expected_ids(runner):
    return [h.get("move_id") for link in runner.links for h in link.hits]


def mismatches(runner):
    out = []
    for got, want in zip(runner.hits, expected_ids(runner)):
        if want is not None and got["move_id"] != int(want, 16):
            out.append(f"0x{got['move_id']:04X} where {want} was expected")
    return out


def report(i, attempts, runner):
    planned = sum(len(link.hits) for link in runner.links)
    pct = round(100 * runner.damage / runner.listed_damage) if runner.listed_damage else 0
    reaction = runner.first_reaction
    hit_kind = "counter hit" if reaction in COUNTER_CODES else f"reaction {reaction}" if reaction is not None else "no hit"
    where = ""
    if runner.status != "done":
        where = f" at link {runner.index + 1}/{len(runner.links)} ({runner.links[min(runner.index, len(runner.links) - 1)].notation})"
    print(f"attempt {i}/{attempts}: {runner.damage} damage vs {runner.listed_damage} listed ({pct}%), "
          f"{len(runner.hits)}/{planned} hits, {runner.status}{where}, opener {hit_kind}", flush=True)
    print(f"  bot moves at each hit: {fmt_ids(runner.hits) or '-'}", flush=True)
    for link, error in runner.errors:
        print(f"  execution error on link {link + 1}: {error}", flush=True)
    for line in mismatches(runner):
        print(f"  move id {line}", flush=True)


def parse_values(key, text):
    if key in INT_KEYS and ":" in text:
        a, b, *step = (int(x) for x in text.split(":"))
        return list(range(a, b + 1, step[0] if step else 1))
    values = ["" if v == "none" else v for v in text.split("|")]
    return [int(v) for v in values] if key in INT_KEYS else values


def parse_sets(items):
    grid = []
    for item in items:
        key, _, text = item.partition("=")
        grid.append((key, parse_values(key, text)))
    return grid


def variant(route, link, setting):
    out = copy.deepcopy(route)
    out["segments"] = out["segments"][:link]
    for key, value in setting.items():
        out["segments"][link - 1][key] = value
    return out


def link_hits(runner, index):
    return [h for h in runner.hits if h["link"] == index]


def print_trace(runner, link):
    rows = runner.trace or []
    start = runner.connects.get(link - 2)
    rows = [r for r in rows if start is None or r["frame"] >= start]
    print(f"  trace from the link {link - 1} connect (frame {start}): frame link pad bot_move free until side "
          f"target_move basic status y distance health reaction", flush=True)
    for r in rows:
        pad = r.get("pad")
        pad = "-" if pad is None else pad[0] + ("+" + "+".join(pad[1]) if pad[1] else "")
        print(f"  {r['frame']:>6} {r['link'] + 1} {pad:>6} 0x{r['bot_move']:04X} {int(r['bot_free'])} {r['bot_until']:>3} "
              f"{r['bot_side']} 0x{r['target_move']:04X} {r['basic_state']:>3} 0x{r['status']:04X} {r['y']:>7} "
              f"{r['distance']:>5} {r['health']:>3} {r['reaction']}", flush=True)


def sweep(gs_iter, seq, route, name, bot, difficulty, link, grid, attempts, wait_reset, trace):
    keys = [k for k, _ in grid]
    expected = route["segments"][link - 1]["hits"][0].get("move_id")
    summary = []
    for combo in itertools.product(*[v for _, v in grid]):
        setting = dict(zip(keys, combo))
        test = variant(route, link, setting)
        label = " ".join(f"{k}={v if v != '' else 'none'}" for k, v in setting.items())
        landed, damage, ids_ok, reached, traced = 0, [], 0, 0, False
        for i in range(attempts):
            gs = wait_settled(gs_iter, bot, wait_reset)
            runner = attempt(gs_iter, seq, test, name, bot, difficulty, gs, trace=trace and not traced)
            hits = link_hits(runner, link - 1)
            ok = runner.status == "done"
            landed += ok
            reach = runner.index >= link - 1
            reached += reach
            damage.append(sum(h["damage"] for h in hits))
            if expected and hits and hits[0]["move_id"] == int(expected, 16):
                ids_ok += 1
            why = f" ({runner.reason})" if runner.reason else ""
            print(f"  {label} #{i + 1}: {runner.status}{why}, link {link} hits {fmt_ids(hits) or '-'}"
                  + ("" if reach else f" (stopped earlier at link {runner.index + 1})"), flush=True)
            if trace and not traced and reach:
                print_trace(runner, link)
                traced = True
        mean = sum(damage) / max(1, len(damage))
        line = f"{label}: {landed}/{reached} landed of the attempts that reached link {link} ({attempts} run), damage mean {mean:.1f}" + (
            f", first hit {expected} {ids_ok}/{attempts}" if expected else "")
        summary.append(line)
        print(line, flush=True)
    print(f"\nsweep of link {link} ({route['segments'][link - 1]['hits'][-1]['command']}):", flush=True)
    for line in summary:
        print("  " + line, flush=True)


def run(reader, pad, route, name, attempts, difficulty, wait_reset, link=None, grid=None, trace=False):
    config = load_config()
    seq = Sequencer(pad, config["input_latency_frames"], difficulty, random.Random(),
                    Timing.from_config(config.get("timing")))
    gs_iter = states(frames(reader, Pacer(), pad.check_kill))
    first = next(gs_iter)
    bot = 1 - first["human_slot"]
    character = first["players"][bot]["character"]
    if character != "kazuya":
        print(f"the pad-controlled dummy (P{bot + 1}) is {character}, not kazuya; pick Kazuya as the practice dummy", flush=True)
        return 2
    print(f"route {name}: {route['guide']}" + (" (experimental)" if route.get("experimental") else ""), flush=True)
    print("links: " + " | ".join(link.notation for link in ComboRunner(route, seq, bot, difficulty).links), flush=True)
    print(f"bot P{bot + 1} kazuya (practice dummy on the pad). Stand still next to him and let go of your stick; "
          f"each attempt starts once both of you have been free for {SETTLE_FRAMES} frames"
          + (" after a practice position reset" if wait_reset else "") + ".", flush=True)
    if route.get("requires") == "counter_hit":
        print("this route needs the opener to counter hit: keep pressing a slow button (for example 4) so df+2 lands "
              "during your startup", flush=True)
    if link is not None:
        sweep(gs_iter, seq, route, name, bot, difficulty, link, grid or [("delay", [0])], attempts, wait_reset, trace)
        pad.release_all()
        return 0
    results = []
    for i in range(1, attempts + 1):
        gs = wait_settled(gs_iter, bot, wait_reset)
        runner = attempt(gs_iter, seq, route, name, bot, difficulty, gs)
        results.append(runner)
        report(i, attempts, runner)
    pad.release_all()
    done = [r for r in results if r.status == "done"]
    damages = [r.damage for r in results]
    listed = results[0].listed_damage if results else 0
    print(f"\n{name}: completed {len(done)}/{len(results)}, damage per attempt {damages}, "
          f"mean {sum(damages) / max(1, len(damages)):.1f} vs {listed} listed (listed is unscaled)", flush=True)
    return 0


class Tee:
    def __init__(self, stream, path):
        self.stream = stream
        self.file = open(path, "w", encoding="utf-8")

    def write(self, text):
        self.stream.write(text)
        self.file.write(text)

    def flush(self):
        self.stream.flush()
        self.file.flush()


def main(argv=None):
    sys.stdout.reconfigure(errors="replace")
    routes = load_routes()["routes"]
    parser = argparse.ArgumentParser(description="Run a Kazuya combo route on the practice dummy and compare damage with the listed damage")
    parser.add_argument("--route", required=True, choices=sorted(routes))
    parser.add_argument("--attempts", type=int, default=None)
    parser.add_argument("--difficulty", type=int, default=5, choices=range(1, 6))
    parser.add_argument("--wait-reset", action="store_true", help="wait for a practice position reset before each attempt")
    parser.add_argument("--link", type=int, help="sweep this link (1-based); the route is cut after it")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUES",
                        help="segment field to sweep for --link: delay=0:20:2, hold=1:4, lead=f,F|f,f|f|none")
    parser.add_argument("--trace", action="store_true", help="print the per-frame trace of the first attempt per value")
    parser.add_argument("--out", help="also write everything printed to this file")
    parser.add_argument("--offsets", default=str(DEFAULT_OFFSETS))
    args = parser.parse_args(argv)
    if args.out:
        sys.stdout = Tee(sys.stdout, args.out)
    route = routes[args.route]
    if args.link is not None and not 1 <= args.link <= len(route["segments"]):
        parser.error(f"--link must be 1..{len(route['segments'])}")
    attempts = args.attempts or (SWEEP_ATTEMPTS if args.link else ATTEMPTS)

    reader = Reader(args.offsets)
    pad = None
    try:
        if not run_gate(reader, args.offsets):
            return 1
        pad = connect_pad()
        return run(reader, pad, route, args.route, attempts, Difficulty.preset(args.difficulty), args.wait_reset,
                   args.link, parse_sets(args.set), args.trace)
    except (KeyboardInterrupt, KillSwitch) as e:
        print(f"stopped: {e}" if str(e) else "stopped: Ctrl+C", flush=True)
        return 1
    finally:
        if pad is not None:
            pad.release_all()
        reader.close()


if __name__ == "__main__":
    sys.exit(main())
