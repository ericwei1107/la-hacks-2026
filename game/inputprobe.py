import argparse
import sys
import time
from collections import Counter

from game import state as st
from game.pacer import Pacer
from game.reader import DEFAULT_OFFSETS, Reader
from game.readout import run_gate

POLL_HZ = 240
HEARTBEAT_S = 1.0


def watch(p):
    return (p.get("move_id"), p.get("dir_held"), p.get("game_buttons"), p.get("health"))


def fmt_player(i, p):
    word = p.get("game_buttons") or 0
    pressed = "+".join(b for b in st.buttons(word, st.PRESSED_SHIFT) if b in "1234") or "-"
    held = "+".join(b for b in st.buttons(word, st.HELD_SHIFT) if b in "1234") or "-"
    d = p.get("dir_held")
    return (f"P{i + 1} move 0x{p.get('move_id', 0):04X} f{p.get('frame_in_move')} dir {st.DIRECTIONS.get(d, '?')}({d}) "
            f"pressed {pressed} held {held} hp {p.get('health')}")


def probe(reader, seconds, log):
    pacer = Pacer(POLL_HZ)
    start = time.monotonic()
    last_beat = start
    prev = [None, None]
    prev_rf = None
    rf_moves = 0
    unreadable = 0
    counts = [Counter(), Counter()]
    while time.monotonic() - start < seconds:
        snap = reader.snapshot()
        now = time.monotonic() - start
        if snap is None:
            unreadable += 1
        else:
            if snap.round_frame != prev_rf:
                rf_moves += 1
                prev_rf = snap.round_frame
            changed = []
            for i, p in enumerate(snap.players):
                w = watch(p)
                old = prev[i]
                if old is not None and w != old:
                    c = counts[i]
                    c["move"] += w[0] != old[0]
                    c["dir"] += w[1] != old[1]
                    c["buttons"] += w[2] != old[2]
                    c["press"] += bool(st.buttons(w[2] or 0, st.PRESSED_SHIFT)) and w[2] != old[2]
                    c["hit"] += (w[3] or 0) < (old[3] or 0)
                    changed.append(i)
                prev[i] = w
            if changed:
                log(f"{now:7.2f}s rf {snap.round_frame} human P{snap.human_slot + 1} | "
                    + " | ".join(("*" if i in changed else " ") + fmt_player(i, p) for i, p in enumerate(snap.players)))
        if now - (last_beat - start) >= HEARTBEAT_S:
            last_beat = time.monotonic()
            log(f"{now:7.2f}s heartbeat: round frame changed {rf_moves} times so far, "
                f"{unreadable} unreadable polls, rf {prev_rf}")
        pacer.wait()
    log("")
    log(f"summary over {seconds:.0f} s: round frame changed {rf_moves} times; {unreadable} polls had no readable players")
    for i, c in enumerate(counts):
        log(f"  P{i + 1}: {c['move']} move id changes, {c['dir']} direction changes, {c['buttons']} button word changes "
            f"({c['press']} with a just-pressed bit), {c['hit']} health drops")
    for i, c in enumerate(counts):
        if c["move"] and not (c["dir"] or c["buttons"]):
            log(f"  P{i + 1}: moves changed but the input fields never did -> only move ids are available for this player")
        elif c["dir"] or c["buttons"]:
            log(f"  P{i + 1}: input fields changed -> inputs are readable for this player")
    if rf_moves <= 1:
        log("  the round frame counter did not move: combocapture and the bot loop wait on it, so they see nothing here")


def main(argv=None):
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Print raw move id, input field and health changes for both players, "
                                                 "without waiting on the round frame counter")
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--out", help="also write the log to this file")
    parser.add_argument("--offsets", default=str(DEFAULT_OFFSETS))
    args = parser.parse_args(argv)
    out = open(args.out, "w", encoding="utf-8") if args.out else None

    def log(text):
        print(text, flush=True)
        if out:
            out.write(text + "\n")
            out.flush()

    reader = Reader(args.offsets)
    try:
        if not run_gate(reader, args.offsets):
            return 1
        log(f"probing for {args.seconds:.0f} s; start the sample combo now. A line prints whenever either player's move id, "
            f"direction, buttons or health changes (* marks who changed).")
        probe(reader, args.seconds, log)
        return 0
    except KeyboardInterrupt:
        log("stopped: Ctrl+C")
        return 1
    finally:
        reader.close()
        if out:
            out.close()


if __name__ == "__main__":
    sys.exit(main())
