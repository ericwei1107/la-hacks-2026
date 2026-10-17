import argparse
import sys
import time

from game.hotloop import frames
from game.pacer import Pacer
from game.pad import KillSwitch, Pad
from game.reader import DEFAULT_OFFSETS, Reader
from game.readout import run_gate

LABELS = ("1", "2", "3", "4", "f", "b", "u", "d", "df", "db", "uf", "ub")
IDLE = 0x8001
HOLD_FRAMES = 4
WATCH_FRAMES = 60
CONNECT_FRAMES = 60
SETTLE_FRAMES = 20
SETTLE_LIMIT = 240
EXPECTED = {
    "kazuya": {"1": 0x659, "2": 0x645, "3": 0x64E, "4": 0x652, "f": 0x5C1, "b": 0x5C6, "d": 0x5DB, "df": 0x5DC, "db": 0x5DD},
    "devil_jin": {"1": 0x643, "2": 0x60E, "3": 0x613, "4": 0x653, "f": 0x59F, "b": 0x5A3, "d": 0x5BC, "db": 0x5BD},
    "king": {"1": 0x652, "2": 0x61E, "3": 0x622, "4": 0x62C, "f": 0x5A7, "b": 0x5AB, "df": 0x5C2},
}
MENU_HOLD_S = 0.1


def split(label):
    return ("n", (label,)) if label.isdigit() else (label, ())


def ids_text(ids):
    return " ".join(f"0x{m:04X}" for m in ids) or "none"


def settle(it, bot):
    calm = 0
    for i, (snap, _) in enumerate(it):
        p = snap.players[bot]
        calm = calm + 1 if p["free_movement"] and p["move_id"] == IDLE else 0
        if calm >= SETTLE_FRAMES or i >= SETTLE_LIMIT:
            return snap


def press_and_watch(it, pad, bot, label):
    direction, buttons = split(label)
    seen = {0: [], 1: []}
    for i, (snap, _) in enumerate(it):
        if i < HOLD_FRAMES:
            pad.apply(direction, buttons, snap.players[bot]["side"])
        elif i == HOLD_FRAMES:
            pad.release_all()
        for slot in (0, 1):
            mv = snap.players[slot]["move_id"]
            if mv != IDLE and (not seen[slot] or seen[slot][-1] != mv):
                seen[slot].append(mv)
        if i >= WATCH_FRAMES:
            return seen, snap


def run_live(reader, pad):
    pacer = Pacer()
    it = frames(reader, pacer, pad.check_kill)
    snap, _ = next(it)
    bot = 1 - snap.human_slot
    character = snap.players[bot]["character"]
    expected = EXPECTED.get(character, {})
    print(f"human P{snap.human_slot + 1} (local info block), bot P{bot + 1} {character}; "
          f"virtual pad connected, waiting {CONNECT_FRAMES} frames for Tekken to see it. Don't touch your stick.", flush=True)
    for i, _ in enumerate(it):
        if i >= CONNECT_FRAMES:
            break
    failures = []
    drove_bot = True
    for label in LABELS:
        snap = settle(it, bot)
        side = "L" if snap.players[bot]["side"] == 0 else "R"
        print(f"[{label:>2}] pressing {label} for {HOLD_FRAMES} frames (bot on {side})", flush=True)
        seen, _ = press_and_watch(it, pad, bot, label)
        want = expected.get(label)
        bot_ids, human_ids = seen[bot], seen[1 - bot]
        if not bot_ids:
            drove_bot = False
        if human_ids:
            drove_bot = False
        verdict = ""
        if want is not None:
            ok = bool(bot_ids) and bot_ids[0] == want
            verdict = f" expected first 0x{want:04X}: {'ok' if ok else 'FAIL'}"
            if not ok and label.isdigit():
                failures.append(label)
        print(f"      bot P{bot + 1} ids {ids_text(bot_ids)}{verdict}"
              + (f"; HUMAN P{2 - bot} also moved: {ids_text(human_ids)}" if human_ids else ""), flush=True)
    pad.release_all()
    print(f"drives the bot block: {'PASS' if drove_bot else 'FAIL'}", flush=True)
    print(f"button ids: {'PASS' if not failures else 'FAIL on ' + ', '.join(failures)}", flush=True)
    return 0 if drove_bot and not failures else 1


def run_blind(pad):
    for label in LABELS:
        direction, buttons = split(label)
        print(f"[{label:>2}] pressing {label}", flush=True)
        pad.apply(direction, buttons, 0)
        time.sleep(HOLD_FRAMES / 60)
        pad.release_all()
        time.sleep(1.0)
        pad.check_kill()
    return 0


def run_menu(pad):
    print("menu mode: type keys separated by spaces (u d l r a b x y start back lb rb), Enter to send, q to quit", flush=True)
    for line in sys.stdin:
        keys = line.split()
        if keys == ["q"]:
            break
        for key in keys:
            try:
                pad.menu(key.split("+"))
            except KeyError:
                print(f"unknown key {key!r}", flush=True)
                continue
            time.sleep(MENU_HOLD_S)
            pad.release_all()
            time.sleep(MENU_HOLD_S)
        print("sent " + " ".join(keys), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Press each pad button once on the virtual 2P pad and check the bot's move ids")
    parser.add_argument("--no-read", action="store_true", help="press without attaching to the game")
    parser.add_argument("--menu", action="store_true", help="interactive menu navigation for joining as 2P")
    parser.add_argument("--offsets", default=str(DEFAULT_OFFSETS))
    args = parser.parse_args(argv)

    if args.menu or args.no_read:
        pad = Pad()
        try:
            return run_menu(pad) if args.menu else run_blind(pad)
        except (KeyboardInterrupt, KillSwitch) as e:
            print(f"stopped: {e or 'Ctrl+C'}", flush=True)
            return 1
        finally:
            pad.release_all()

    reader = Reader(args.offsets)
    pad = None
    try:
        if not run_gate(reader, args.offsets):
            return 1
        pad = Pad()
        return run_live(reader, pad)
    except (KeyboardInterrupt, KillSwitch) as e:
        print(f"stopped: {e or 'Ctrl+C'}", flush=True)
        return 1
    finally:
        if pad is not None:
            pad.release_all()
        reader.close()


if __name__ == "__main__":
    sys.exit(main())
