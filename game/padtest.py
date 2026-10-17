import argparse
import sys
import threading
import time

from game import state as st
from game.hotloop import frames
from game.pacer import Pacer
from game.pad import KillSwitch, absolute, connect_pad
from game.padserver import MENU_HELP, press_menu
from game.reader import DEFAULT_OFFSETS, Reader
from game.readout import run_gate

LABELS = ("1", "2", "3", "4", "f", "F", "b", "B", "u", "d", "df", "db", "uf", "ub")
IDLE = 0x8001
TAP_FRAMES = 4
HOLD_FRAMES = 30
WATCH_FRAMES = 60
CONNECT_FRAMES = 60
SETTLE_FRAMES = 20
SETTLE_LIMIT = 240
EXPECTED = {
    "kazuya": {"1": 0x659, "2": 0x645, "3": 0x64E, "4": 0x652, "f": 0x5C1, "b": 0x5C6, "d": 0x5DB, "df": 0x5DC, "db": 0x5DD},
    "devil_jin": {"1": 0x643, "2": 0x60E, "3": 0x613, "4": 0x653, "f": 0x59F, "b": 0x5A3, "d": 0x5BC, "db": 0x5BD},
    "king": {"1": 0x652, "2": 0x61E, "3": 0x622, "4": 0x62C, "f": 0x5A7, "b": 0x5AB, "df": 0x5C2},
}
RAW_BITS = (("U", 0x1), ("D", 0x2), ("L", 0x4), ("R", 0x8), ("1", 0x4000), ("2", 0x8000), ("3", 0x1000), ("4", 0x2000))
SCREEN = {"u": "U", "d": "D", "left": "L", "right": "R"}


def split(label):
    if label.isdigit():
        return "n", (label,), TAP_FRAMES
    return label.lower(), (), HOLD_FRAMES if label.isupper() else TAP_FRAMES


def ids_text(ids):
    return " ".join(f"0x{m:04X}" for m in ids) or "none"


def raw_text(word):
    return "".join(name for name, bit in RAW_BITS if word & bit) or "-"


def held_text(word):
    return "".join(st.buttons(word, st.HELD_SHIFT)) or "-"


def expected_raw(direction, buttons, side):
    return "".join(name for name, _ in RAW_BITS if name in {SCREEN[d] for d in absolute(direction, side)} | set(buttons)) or "-"


def settle(it, bot):
    calm = 0
    for i, (snap, _) in enumerate(it):
        p = snap.players[bot]
        calm = calm + 1 if p["free_movement"] and p["move_id"] == IDLE else 0
        if calm >= SETTLE_FRAMES or i >= SETTLE_LIMIT:
            return snap


def note(seq, value):
    if not seq or seq[-1] != value:
        seq.append(value)


def press_and_watch(it, pad, bot, label):
    direction, buttons, hold = split(label)
    seen = {slot: {"ids": [], "dir": [], "raw": [], "held": []} for slot in (0, 1)}
    for i, (snap, _) in enumerate(it):
        if i < hold:
            pad.apply(direction, buttons, snap.players[bot]["side"])
        elif i == hold:
            pad.release_all()
        for slot in (0, 1):
            p = snap.players[slot]
            if p["move_id"] != IDLE:
                note(seen[slot]["ids"], p["move_id"])
            if i < hold + 2:
                note(seen[slot]["dir"], st.DIRECTIONS.get(p["dir_held"], f"?{p['dir_held']}"))
                note(seen[slot]["raw"], raw_text(p["raw_buttons"]))
                note(seen[slot]["held"], held_text(p["game_buttons"]))
        if i >= hold + WATCH_FRAMES:
            return seen


def input_landed(seen, direction, buttons, want_raw):
    if buttons:
        return any(set(buttons) <= set(h) for h in seen["held"])
    return direction in seen["dir"] and want_raw in seen["raw"]


def input_idle(seen):
    return set(seen["dir"]) <= {"n"} and set(seen["raw"]) <= {"-"} and set(seen["held"]) <= {"-"}


def run_live(reader, pad):
    pacer = Pacer()
    it = frames(reader, pacer, pad.check_kill)
    snap, _ = next(it)
    bot = 1 - snap.human_slot
    character = snap.players[bot]["character"]
    expected = EXPECTED.get(character, {})
    print(f"human P{snap.human_slot + 1} (local info block), bot P{bot + 1} {character}. Don't touch your stick.", flush=True)
    if not pad.remote:
        print(f"waiting {CONNECT_FRAMES} frames for Tekken to see the new pad", flush=True)
        for i, _ in enumerate(it):
            if i >= CONNECT_FRAMES:
                break
    failures = []
    landed_all = True
    human_quiet = True
    for label in LABELS:
        snap = settle(it, bot)
        side = snap.players[bot]["side"]
        direction, buttons, hold = split(label)
        want_raw = expected_raw(direction, buttons, side)
        print(f"[{label:>2}] {'holding' if hold > TAP_FRAMES else 'tapping'} {label.lower()} for {hold} frames "
              f"(bot on {'L' if side == 0 else 'R'}, expect screen {want_raw})", flush=True)
        seen = press_and_watch(it, pad, bot, label)
        b, h = seen[bot], seen[1 - bot]
        landed = input_landed(b, direction, buttons, want_raw)
        quiet = input_idle(h)
        landed_all &= landed
        human_quiet &= quiet
        want = expected.get(label)
        verdict = ""
        if want is not None:
            ok = bool(b["ids"]) and b["ids"][0] == want
            verdict = f" (expected first 0x{want:04X}: {'ok' if ok else 'FAIL'})"
            if not ok:
                failures.append(label)
        print(f"      bot P{bot + 1} input: dir {'>'.join(b['dir'])} screen {'>'.join(b['raw'])} buttons {'>'.join(b['held'])} "
              f"{'ok' if landed else 'MISSING'}; ids {ids_text(b['ids'])}{verdict}", flush=True)
        if not quiet:
            print(f"      HUMAN P{2 - bot} input moved: dir {'>'.join(h['dir'])} screen {'>'.join(h['raw'])} "
                  f"buttons {'>'.join(h['held'])}", flush=True)
    pad.release_all()
    print(f"pad input lands on the bot block: {'PASS' if landed_all else 'FAIL'}", flush=True)
    print(f"human block input untouched: {'PASS' if human_quiet else 'FAIL'}", flush=True)
    print(f"button ids: {'PASS' if not failures else 'FAIL on ' + ', '.join(failures)}", flush=True)
    return 0 if landed_all and human_quiet and not failures else 1


def run_blind(pad):
    for label in LABELS:
        direction, buttons, hold = split(label)
        print(f"[{label:>2}] pressing {label}", flush=True)
        pad.apply(direction, buttons, 0)
        time.sleep(hold / 60)
        pad.release_all()
        time.sleep(1.0)
        pad.check_kill()
    return 0


def run_menu(pad):
    print(MENU_HELP, flush=True)
    lock = threading.Lock()
    for line in sys.stdin:
        if line.strip() == "q":
            break
        keys = press_menu(pad, lock, line)
        if keys:
            print("sent " + " ".join(keys), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Press each pad button once on the virtual 2P pad and check the bot's move ids")
    parser.add_argument("--no-read", action="store_true", help="press without attaching to the game")
    parser.add_argument("--menu", action="store_true", help="interactive menu navigation for joining as 2P")
    parser.add_argument("--offsets", default=str(DEFAULT_OFFSETS))
    args = parser.parse_args(argv)

    if args.menu or args.no_read:
        pad = connect_pad()
        try:
            return run_menu(pad) if args.menu else run_blind(pad)
        except (KeyboardInterrupt, KillSwitch) as e:
            print(f"stopped: {e}" if str(e) else "stopped: Ctrl+C", flush=True)
            return 1
        finally:
            pad.release_all()

    reader = Reader(args.offsets)
    pad = None
    try:
        if not run_gate(reader, args.offsets):
            return 1
        pad = connect_pad()
        return run_live(reader, pad)
    except (KeyboardInterrupt, KillSwitch) as e:
        print(f"stopped: {e}" if str(e) else "stopped: Ctrl+C", flush=True)
        return 1
    finally:
        if pad is not None:
            pad.release_all()
        reader.close()


if __name__ == "__main__":
    sys.exit(main())
