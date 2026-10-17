import argparse
import random
import sys

from game import state as st
from game.difficulty import Difficulty
from game.hotloop import frames
from game.notation import NotationError, Timing, compile_notation, describe
from game.pacer import Pacer
from game.pad import KillSwitch, connect_pad, load_config
from game.padtest import IDLE, settle
from game.reader import DEFAULT_OFFSETS, Reader
from game.readout import run_gate
from game.sequencer import Sequencer

WATCH_FRAMES = 90


def mask_text(mask):
    d, b = mask
    return "+".join(([] if d == "n" and b else [d]) + list(b))


def perform_once(it, seq, bot, notation, watch):
    snap = settle(it, bot)
    side = "L" if snap.players[bot]["side"] == 0 else "R"
    move = seq.submit(notation, frame=snap.round_frame)
    seq.applied.clear()
    timeline = []
    last_id = None
    attacks = []
    start = None
    for snap, _ in it:
        gs = st.build_state(snap.players, snap.human_slot, snap.round_frame, "perform")
        if gs is None:
            continue
        p = gs["players"][bot]
        seq.on_frame(gs["frame"], p)
        if start is None:
            start = move.start_frame
        dt = gs["frame"] - start if start is not None else 0
        if p["move_id"] != last_id:
            last_id = p["move_id"]
            if p["move_id"] != IDLE:
                timeline.append((dt, f"bot mv 0x{p['move_id']:04X} {p['hit_level']}"))
                if p["hit_level"] != "none" and (not attacks or attacks[-1] != p["move_id"]):
                    attacks.append(p["move_id"])
        if start is not None and dt >= watch and not seq.busy():
            break
    for frame, mask in seq.applied:
        timeline.append((frame - start, f"pad {mask_text(mask)}"))
    seq.pop_finished()
    return side, move, sorted(timeline, key=lambda e: (e[0], not e[1].startswith("pad"))), attacks


def run(reader, pad, args, timing):
    config = load_config()
    difficulty = Difficulty.preset(args.difficulty) if args.difficulty else None
    seq = Sequencer(pad, config["input_latency_frames"], difficulty, random.Random(args.seed), timing)
    it = frames(reader, Pacer(), pad.check_kill)
    snap, _ = next(it)
    bot = 1 - snap.human_slot
    print(f"bot P{bot + 1} {snap.players[bot]['character']}: {args.notation!r} -> {describe(compile_notation(args.notation, timing), timing)!r}, "
          f"{len(compile_notation(args.notation, timing))} frames, {args.repeat} repeat(s)", flush=True)
    for n in range(1, args.repeat + 1):
        side, move, timeline, attacks = perform_once(it, seq, bot, args.notation, args.watch)
        print(f"#{n} bot on {side}" + (f", execution error: {move.error}" if move.error else ""), flush=True)
        for dt, text in timeline:
            print(f"  +{dt:>3} {text}", flush=True)
        print(f"  attack move ids in order: {' '.join(f'0x{m:04X}' for m in attacks) or 'none'}", flush=True)
    pad.release_all()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Perform a Tekken notation string on the bot and print the move-id timeline")
    parser.add_argument("notation")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--watch", type=int, default=WATCH_FRAMES)
    parser.add_argument("--difficulty", type=int, choices=range(1, 6), help="apply that preset's execution error")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--string-gap", type=int)
    parser.add_argument("--press-frames", type=int)
    parser.add_argument("--offsets", default=str(DEFAULT_OFFSETS))
    args = parser.parse_args(argv)

    overrides = dict(load_config().get("timing", {}))
    if args.string_gap is not None:
        overrides["string_gap"] = args.string_gap
    if args.press_frames is not None:
        overrides["press_frames"] = args.press_frames
    timing = Timing.from_config(overrides)
    try:
        compile_notation(args.notation, timing)
    except NotationError as e:
        print(f"bad notation: {e}", flush=True)
        return 2

    reader = Reader(args.offsets)
    pad = None
    try:
        if not run_gate(reader, args.offsets):
            return 1
        pad = connect_pad()
        return run(reader, pad, args, timing)
    except (KeyboardInterrupt, KillSwitch) as e:
        print(f"stopped: {e}" if str(e) else "stopped: Ctrl+C", flush=True)
        return 1
    finally:
        if pad is not None:
            pad.release_all()
        reader.close()


if __name__ == "__main__":
    sys.exit(main())
