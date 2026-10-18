import argparse
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
SETTLE_FRAMES = 30
TIMEOUT_FRAMES = 900
COUNTER_CODES = {code for code, name in st.REACTIONS.items() if name == "counter_hit"}


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
    for gs in gs_iter:
        if last is not None and gs["frame"] < last:
            reset = True
            run = 0
        last = gs["frame"]
        run = run + 1 if calm(gs, bot) else 0
        if reset and run >= SETTLE_FRAMES:
            return gs
    return None


def attempt(gs_iter, seq, route, name, bot, difficulty, first):
    runner = ComboRunner(route, seq, bot, difficulty, name=name)
    start = first["frame"]
    gs = first
    while True:
        runner.on_state(gs)
        seq.on_frame(gs["frame"], gs["players"][bot])
        if runner.finished:
            break
        if gs["frame"] - start > TIMEOUT_FRAMES:
            runner.stop(gs["frame"])
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


def run(reader, pad, route, name, attempts, difficulty, wait_reset):
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
    print(f"route {name}: {route['guide']}", flush=True)
    print("links: " + " | ".join(link.notation for link in ComboRunner(route, seq, bot, difficulty).links), flush=True)
    print(f"bot P{bot + 1} kazuya (practice dummy on the pad). Stand still next to him and let go of your stick; "
          f"each attempt starts once both of you have been free for {SETTLE_FRAMES} frames"
          + (" after a practice position reset" if wait_reset else "") + ".", flush=True)
    if route.get("requires") == "counter_hit":
        print("this route needs the opener to counter hit: keep pressing a slow button (for example 4) so df+2 lands "
              "during your startup", flush=True)
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


def main(argv=None):
    routes = load_routes()["routes"]
    parser = argparse.ArgumentParser(description="Run a Kazuya combo route on the practice dummy and compare damage with the listed damage")
    parser.add_argument("--route", required=True, choices=sorted(routes))
    parser.add_argument("--attempts", type=int, default=ATTEMPTS)
    parser.add_argument("--difficulty", type=int, default=5, choices=range(1, 6))
    parser.add_argument("--wait-reset", action="store_true", help="wait for a practice position reset before each attempt")
    parser.add_argument("--offsets", default=str(DEFAULT_OFFSETS))
    args = parser.parse_args(argv)

    reader = Reader(args.offsets)
    pad = None
    try:
        if not run_gate(reader, args.offsets):
            return 1
        pad = connect_pad()
        return run(reader, pad, routes[args.route], args.route, args.attempts,
                   Difficulty.preset(args.difficulty), args.wait_reset)
    except (KeyboardInterrupt, KillSwitch) as e:
        print(f"stopped: {e}" if str(e) else "stopped: Ctrl+C", flush=True)
        return 1
    finally:
        if pad is not None:
            pad.release_all()
        reader.close()


if __name__ == "__main__":
    sys.exit(main())
