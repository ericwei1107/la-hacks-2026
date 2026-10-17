import argparse
import math
import random
import sys

from game import state as st
from game.hotloop import frames
from game.notation import NotationError, Timing, compile_notation
from game.pacer import Pacer
from game.pad import KillSwitch, connect_pad, load_config
from game.reader import DEFAULT_OFFSETS, Reader
from game.readout import run_gate
from game.sequencer import Sequencer

INPUTS = ("wait", "u", "f", "b", "d", "1", "2", "3", "4", "1+2", "3+4", "U", "B")
DELAY_FRAMES = 2
READY_STABLE = 2
FACES = {"up": 12, "down": 13}
FACE_NAMES = {12: "face up", 13: "face down"}
WATCH_FRAMES = 150


def geometry(gs, bot):
    b, h = gs["players"][bot], gs["players"][1 - bot]
    return b["x"], b["z"], h["x"], h["z"]


def displacement(start, end):
    bx0, bz0, hx0, hz0 = start
    bx1, bz1, _, _ = end
    ax, az = bx0 - hx0, bz0 - hz0
    norm = math.hypot(ax, az) or 1.0
    ux, uz = ax / norm, az / norm
    dx, dz = bx1 - bx0, bz1 - bz0
    away = dx * ux + dz * uz
    side = dx * -uz + dz * ux
    return round(math.hypot(ax, az)), round(away), round(side)


def states(it, sid="getuptest"):
    for snap, _ in it:
        gs = st.build_state(snap.players, snap.human_slot, snap.round_frame, sid)
        if gs is not None:
            yield gs


def wait_downed(gs_iter, bot):
    for gs in gs_iter:
        if gs["players"][bot]["status"] & st.DOWNED_BIT:
            return gs


def face_ok(p, face):
    return face == "any" or p["basic_state"] == FACES[face]


def probe(gs_iter, seq, bot, notation, delay, watch, face="any"):
    down = wait_downed(gs_iter, bot)
    p = down["players"][bot]
    pre = [(0, p["move_id"])]
    free_at = None
    disturbed = False
    health = p["health"]
    run = 0
    wrong_face_noted = False
    ready_at = None
    start_geo = None
    for gs in gs_iter:
        p = gs["players"][bot]
        dt = gs["frame"] - down["frame"]
        if p["free_movement"] and free_at is None:
            free_at = dt
        if pre[-1][1] != p["move_id"]:
            pre.append((dt, p["move_id"]))
            run = 0
        seq.on_frame(gs["frame"], p)
        if ready_at is None and not p["status"] & st.DOWNED_BIT:
            print(f"  left the ground at +{dt} before the input ({fmt_ids(pre)}): hit off the floor or got up; "
                  f"waiting for him to land again", flush=True)
            return probe(gs_iter, seq, bot, notation, delay, watch, face)
        if st.lying(p) and not face_ok(p, face):
            if not wrong_face_noted:
                print(f"  lying {FACE_NAMES.get(p['basic_state'], 'basic ' + str(p['basic_state']))} (0x{p['move_id']:04X}); "
                      f"waiting until he is {FACE_NAMES[FACES[face]]}. Flip him with another move, then let go", flush=True)
                wrong_face_noted = True
            run = 0
        else:
            run = run + 1 if st.lying(p) else 0
        if ready_at is None and run >= READY_STABLE:
            ready_at = dt
            info = {"basic_state": p["basic_state"], "down_move": p["move_id"], "facing": p["facing"], "side": p["side"]}
        if ready_at is not None and dt >= ready_at + delay:
            start_geo = geometry(gs, bot)
            start_frame = gs["frame"]
            break
    health = gs["players"][bot]["health"]
    if notation != "wait":
        seq.submit(notation, force=True, frame=start_frame, error=False)
    timeline = []
    up_at = None
    attack = None
    end_geo = start_geo
    act_at = None
    for gs in gs_iter:
        p = gs["players"][bot]
        dt = gs["frame"] - start_frame
        seq.on_frame(gs["frame"], p)
        if p["health"] < health and act_at is None:
            disturbed = True
        health = p["health"]
        if not timeline or timeline[-1][1] != p["move_id"]:
            timeline.append((dt, p["move_id"], p["hit_level"]))
        if up_at is None and not p["status"] & st.DOWNED_BIT:
            up_at = dt
        if attack is None and p["hit_level"] != "none":
            attack = (dt, p["move_id"], p["hit_level"])
        if act_at is None and up_at is not None and p["free_movement"]:
            act_at = dt
        end_geo = geometry(gs, bot)
        if dt >= watch and not seq.busy():
            break
    dist, away, side = displacement(start_geo, end_geo)
    return {**info, "pre": pre, "ready_at": ready_at, "free_while_down": free_at, "timeline": timeline, "up_at": up_at, "act_at": act_at,
            "attack": attack, "distance": dist, "away": away, "lateral": side, "disturbed": disturbed}


def fmt_ids(items):
    return " ".join(f"+{dt}:0x{mv:04X}" + (f"({lvl})" if lvl and lvl != "none" else "") for dt, mv, *rest in items
                    for lvl in [rest[0] if rest else None])


def run(reader, pad, inputs, delay, watch, face="any"):
    config = load_config()
    seq = Sequencer(pad, config["input_latency_frames"], None, random.Random(0), Timing.from_config(config.get("timing")))
    it = frames(reader, Pacer(), pad.check_kill)
    gs_iter = states(it)
    first = next(gs_iter)
    bot = 1 - first["human_slot"]
    wanted = "" if face == "any" else f" {FACE_NAMES[FACES[face]]}"
    print(f"bot P{bot + 1} {first['players'][bot]['character']}. For each input: knock Kazuya down{wanted} (a throw is easiest"
          f"{', then another move to flip him' if face == 'down' else ''}), "
          f"then let go of your stick. The bot performs the input {delay} frames after he settles into his{wanted} lying loop "
          f"(downed, not thrown, a 0x80xx move longer than 1 frame); watching {watch} frames.", flush=True)
    rows = []
    for notation in inputs:
        print(f"\n[{notation}] waiting for a knockdown...", flush=True)
        r = probe(gs_iter, seq, bot, notation, delay, watch, face)
        rows.append((notation, r))
        flag = "  DISTURBED (bot lost health; redo this one)" if r["disturbed"] else ""
        free = f"free_movement at +{r['free_while_down']}" if r["free_while_down"] is not None else "never free"
        print(f"  knocked down: {fmt_ids(r['pre'])}; lying in 0x{r['down_move']:04X} (basic_state {r['basic_state']}) from +{r['ready_at']}, "
              f"input at +{r['ready_at'] + delay}; {free}", flush=True)
        print(f"  after input: {fmt_ids(r['timeline'])}", flush=True)
        print(f"  downed bit cleared at +{r['up_at']}, actionable at +{r['act_at']}, "
              f"attack {('0x%04X %s at +%d' % (r['attack'][1], r['attack'][2], r['attack'][0])) if r['attack'] else 'none'}, "
              f"moved {r['away']:+d} mm away from you and {r['lateral']:+d} mm sideways (distance was {r['distance']} mm){flag}", flush=True)
    pad.release_all()
    print("\nsummary (input: up at, actionable at, attack, away mm, sideways mm):", flush=True)
    for notation, r in rows:
        attack = f"0x{r['attack'][1]:04X} {r['attack'][2]}" if r["attack"] else "-"
        face = {12: "face up", 13: "face down"}.get(r["basic_state"], f"basic {r['basic_state']}")
        print(f"  {notation:>5} ({face}, lying 0x{r['down_move']:04X}): up +{r['up_at']}, act +{r['act_at']}, attack {attack}, "
              f"away {r['away']:+d}, sideways {r['lateral']:+d}"
              + (" DISTURBED" if r["disturbed"] else ""), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Probe what each grounded input does after the bot is knocked down")
    parser.add_argument("--inputs", default=" ".join(INPUTS), help="inputs separated by spaces, e.g. \"u b 1+2\"")
    parser.add_argument("--face", default="any", choices=("any", "up", "down"),
                        help="only press once the bot is lying this way up (basic_state 12 face up, 13 face down)")
    parser.add_argument("--delay", type=int, default=DELAY_FRAMES, help="frames after the bot settles into its lying loop before the input")
    parser.add_argument("--watch", type=int, default=WATCH_FRAMES)
    parser.add_argument("--offsets", default=str(DEFAULT_OFFSETS))
    args = parser.parse_args(argv)

    inputs = args.inputs.split()
    timing = Timing.from_config(load_config().get("timing"))
    for notation in inputs:
        if notation != "wait":
            try:
                compile_notation(notation, timing)
            except NotationError as e:
                print(f"bad input {notation!r}: {e}", flush=True)
                return 2

    reader = Reader(args.offsets)
    pad = None
    try:
        if not run_gate(reader, args.offsets):
            return 1
        pad = connect_pad()
        return run(reader, pad, inputs, args.delay, args.watch, args.face)
    except (KeyboardInterrupt, KillSwitch) as e:
        print(f"stopped: {e}" if str(e) else "stopped: Ctrl+C", flush=True)
        return 1
    finally:
        if pad is not None:
            pad.release_all()
        reader.close()


if __name__ == "__main__":
    sys.exit(main())
