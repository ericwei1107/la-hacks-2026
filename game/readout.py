import argparse
import sys
import time

from game.reader import DEFAULT_OFFSETS, Reader

POLL_HZ = 1000
SPIN_MARGIN = 0.0006
SIDES = {0: "L", 1: "R"}


def fmt_check(check):
    return f"  [{'PASS' if check.ok else 'FAIL'}] {check.name:<20} {check.detail}"


def fmt_player(index, p, human_slot):
    mark = "*" if index == human_slot else " "
    hp = "?" if p["health"] is None else p["health"]
    x, _, z = p["position"]
    level = p["hit_level_name"] or f"0x{p['hit_level']:08X}"
    return (
        f"P{index + 1}{mark} {p['character']}({p['character_id']}) hp {hp:>3} "
        f"side {SIDES.get(p['side'], p['side'])} x {x:7.0f} z {z:7.0f} "
        f"mv 0x{p['move_id']:04X} f {p['frame_in_move']:>4} lvl {level}"
    )


def fmt_line(snap):
    head = f"rf {snap.round_frame:>6}  human P{snap.human_slot + 1}"
    return " | ".join([head] + [fmt_player(i, p, snap.human_slot) for i, p in enumerate(snap.players)])


def run(reader, every):
    period = 1.0 / POLL_HZ
    polls = 0
    frames = 0
    gaps = 0
    resets = 0
    prev = None
    last_print = None
    waiting = False
    start = time.perf_counter()
    deadline = start
    try:
        while True:
            rf = reader.poll_round_frame()
            polls += 1
            if rf is None:
                reader.resolve_blocks()
                reader.resolve_human()
                if not waiting:
                    print("players not readable; waiting for a match", flush=True)
                    waiting = True
            elif rf != prev:
                waiting = False
                if prev is not None:
                    if rf < prev:
                        resets += 1
                    elif rf - prev > 1:
                        gaps += rf - prev - 1
                frames += 1
                prev = rf
                if last_print is None or rf < last_print or rf - last_print >= every:
                    snap = reader.snapshot()
                    if snap is not None:
                        print(fmt_line(snap), flush=True)
                        last_print = rf
            deadline += period
            delay = deadline - time.perf_counter()
            if delay <= -period:
                deadline = time.perf_counter()
            while delay > 0:
                time.sleep(delay - SPIN_MARGIN if delay > SPIN_MARGIN else 0)
                delay = deadline - time.perf_counter()
    except KeyboardInterrupt:
        elapsed = time.perf_counter() - start
        print(
            f"stopped: {frames} frame changes, {gaps} skipped frames, {resets} counter resets, "
            f"{polls / elapsed:.0f} polls/s over {elapsed:.1f} s, {reader.discarded_health} health reads discarded",
            flush=True,
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kumite read-only Tekken 8 state readout")
    parser.add_argument("--offsets", default=str(DEFAULT_OFFSETS))
    parser.add_argument("--every", type=int, default=10)
    args = parser.parse_args(argv)

    reader = Reader(args.offsets)
    print(f"gate ({args.offsets})", flush=True)
    try:
        result = reader.gate(log=lambda c: print(fmt_check(c), flush=True))
        if not result.ok:
            print("GATE FAILED: refusing to run", flush=True)
            return 1
        print("GATE PASSED", flush=True)
        run(reader, args.every)
        return 0
    finally:
        reader.close()


if __name__ == "__main__":
    sys.exit(main())
