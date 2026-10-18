import argparse
import statistics
import sys
from collections import Counter

from game import state as st
from game.hotloop import frames
from game.pacer import Pacer
from game.pad import KillSwitch, connect_pad, load_config, save_config
from game.padtest import CONNECT_FRAMES, EXPECTED, IDLE, settle
from game.reader import DEFAULT_OFFSETS, Reader
from game.readout import run_gate

RELEASE_AFTER = 3
TIMEOUT_FRAMES = 30


def trial(it, pad, bot, want):
    snap, _ = next(it)
    f0 = snap.round_frame
    pad.apply("n", ("1",), snap.players[bot]["side"])
    seen_input = None
    for snap, gap in it:
        p = snap.players[bot]
        dt = snap.round_frame - f0
        if dt == RELEASE_AFTER:
            pad.release_all()
        if seen_input is None and "1" in st.buttons(p["game_buttons"], st.HELD_SHIFT):
            seen_input = dt
        if p["move_id"] != IDLE:
            pad.release_all()
            if want is not None and p["move_id"] != want:
                return None, seen_input, f"first id 0x{p['move_id']:04X}, not the jab 0x{want:04X}"
            return dt, seen_input, None
        if dt < 0 or gap:
            pad.release_all()
            return None, seen_input, "round frame jumped (reset or skipped frame)"
        if dt >= TIMEOUT_FRAMES:
            pad.release_all()
            return None, seen_input, f"no move id change within {TIMEOUT_FRAMES} frames"


def histogram(values):
    counts = Counter(values)
    return "\n".join(f"  {v:>2} frames | {'#' * counts[v]} {counts[v]}" for v in range(min(values), max(values) + 1))


def run(reader, pad, trials, save):
    pacer = Pacer()
    it = frames(reader, pacer, pad.check_kill)
    snap, _ = next(it)
    bot = 1 - snap.human_slot
    character = snap.players[bot]["character"]
    want = EXPECTED.get(character, {}).get("1")
    print(f"bot P{bot + 1} {character}: pressing 1 on the poll right after a round-frame change, "
          f"{trials} trials. Don't touch your stick.", flush=True)
    if not pad.remote:
        for i, _ in enumerate(it):
            if i >= CONNECT_FRAMES:
                break
    move_lat, input_lat, discarded = [], [], []
    while len(move_lat) < trials:
        settle(it, bot)
        lat, seen, why = trial(it, pad, bot, want)
        n = len(move_lat) + len(discarded) + 1
        if lat is None:
            discarded.append(why)
            print(f"  trial {n:>2}: discarded ({why})", flush=True)
            if len(discarded) > trials:
                print("too many discarded trials; stopping", flush=True)
                break
            continue
        move_lat.append(lat)
        if seen is not None:
            input_lat.append(seen)
        print(f"  trial {n:>2}: button seen by the game after {seen} frame(s), move id changed after {lat} frame(s)", flush=True)
    pad.release_all()
    if not move_lat:
        print("no valid trials", flush=True)
        return 1
    median = round(statistics.median(move_lat))
    print("press -> move id change, round frames:")
    print(histogram(move_lat))
    print(f"min {min(move_lat)}, median {statistics.median(move_lat)}, max {max(move_lat)} over {len(move_lat)} trials, "
          f"{len(discarded)} discarded", flush=True)
    if input_lat:
        print(f"press -> button held in 0x28B0: min {min(input_lat)}, median {statistics.median(input_lat)}, max {max(input_lat)}", flush=True)
    if save:
        config = load_config()
        old = config.get("input_latency_frames")
        config["input_latency_frames"] = median
        save_config(config)
        print(f"saved input_latency_frames = {median} to game/pad.json (was {old})", flush=True)
    else:
        print(f"median {median}; rerun with --save to store it in game/pad.json", flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure round frames from a pad press to the bot's move id change")
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--offsets", default=str(DEFAULT_OFFSETS))
    args = parser.parse_args(argv)

    reader = Reader(args.offsets)
    pad = None
    try:
        if not run_gate(reader, args.offsets):
            return 1
        pad = connect_pad()
        return run(reader, pad, args.trials, args.save)
    except (KeyboardInterrupt, KillSwitch) as e:
        print(f"stopped: {e}" if str(e) else "stopped: Ctrl+C", flush=True)
        return 1
    finally:
        if pad is not None:
            pad.release_all()
        reader.close()


if __name__ == "__main__":
    sys.exit(main())
