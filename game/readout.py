import argparse
import sys

from game.pacer import Pacer
from game.reader import DEFAULT_OFFSETS, Reader

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


def run_gate(reader, label):
    print(f"gate ({label})", flush=True)
    result = reader.gate(log=lambda c: print(fmt_check(c), flush=True))
    print("GATE PASSED" if result.ok else "GATE FAILED: refusing to run", flush=True)
    return result.ok


def run(reader, every):
    pacer = Pacer()
    frames = 0
    gaps = 0
    resets = 0
    prev = None
    last_print = None
    waiting = False
    try:
        while True:
            rf = reader.poll_round_frame()
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
            pacer.wait()
    except KeyboardInterrupt:
        elapsed, rate = pacer.rate()
        print(
            f"stopped: {frames} frame changes, {gaps} skipped frames, {resets} counter resets, "
            f"{rate:.0f} polls/s over {elapsed:.1f} s, {reader.discarded_health} health reads discarded",
            flush=True,
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kumite read-only Tekken 8 state readout")
    parser.add_argument("--offsets", default=str(DEFAULT_OFFSETS))
    parser.add_argument("--every", type=int, default=10)
    args = parser.parse_args(argv)

    reader = Reader(args.offsets)
    try:
        if not run_gate(reader, args.offsets):
            return 1
        run(reader, args.every)
        return 0
    finally:
        reader.close()


if __name__ == "__main__":
    sys.exit(main())
