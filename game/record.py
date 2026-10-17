import argparse
import sys
from collections import Counter
from datetime import datetime, timezone

from game import state as st
from game.pacer import Pacer
from game.reader import DEFAULT_OFFSETS, Reader
from game.readout import run_gate
from game.recorder import Recorder, iso_utc, result_text, session_meta


def fmt_event(ev):
    parts = [f"r{ev['round']} f{ev['frame']:>6} {ev['kind']:<12}"]
    if "actor" in ev:
        parts.append(f"P{ev['actor'] + 1}" + (f"->P{ev['target'] + 1}" if "target" in ev else ""))
    if "move_id" in ev:
        parts.append(f"mv 0x{ev['move_id']:04X}")
    if "hit_level" in ev:
        parts.append(ev["hit_level"])
    if ev.get("frame_advantage") is not None:
        parts.append(f"adv {ev['frame_advantage']:+d}")
    if "damage" in ev:
        parts.append(f"dmg {ev['damage']}")
    if ev.get("detail"):
        parts.append(" ".join(f"{k}={v}" for k, v in ev["detail"].items() if not k.startswith(("attacker_", "defender_"))))
    return " ".join(parts)


def wait_snapshot(reader, pacer):
    while True:
        snap = reader.snapshot()
        if snap is not None:
            return snap
        pacer.wait()


def record(reader, args):
    pacer = Pacer()
    snap = wait_snapshot(reader, pacer)
    human = snap.human_slot
    human_char = snap.players[human]["character"]
    bot_char = snap.players[1 - human]["character"]
    if bot_char != args.bot:
        print(f"warning: --bot {args.bot} but the opponent block holds {bot_char}; recording {bot_char}", flush=True)
    started = datetime.now(timezone.utc)
    sid = st.session_id(started, args.player, human_char, bot_char)
    meta = session_meta(sid, started, args.player, human, human_char, bot_char, args.difficulty, args.mode, reader.game["version"], args.stage)
    recorder = Recorder(meta)
    tracker = st.Tracker(sid)
    print(f"recording {recorder.recording_path} (human P{human + 1} {human_char} vs {bot_char}); Ctrl+C to stop", flush=True)

    frames = 0
    gaps = 0
    skipped_states = 0
    prev = None
    try:
        while True:
            rf = reader.poll_round_frame()
            if rf is not None and rf != prev:
                snap = reader.snapshot()
                if snap is not None and snap.round_frame != prev:
                    if prev is not None and snap.round_frame > prev + 1:
                        gaps += snap.round_frame - prev - 1
                    prev = snap.round_frame
                    gs = st.build_state(snap.players, snap.human_slot, snap.round_frame, sid)
                    if gs is None:
                        skipped_states += 1
                    else:
                        frames += 1
                        events = tracker.step(gs)
                        recorder.events(events)
                        recorder.state(gs)
                        for ev in events:
                            print(fmt_event(ev), flush=True)
                        if any(ev["kind"] == "round_end" for ev in events):
                            recorder.write_session(tracker.rounds)
            elif rf is None:
                reader.resolve_blocks()
                reader.resolve_human()
            recorder.tick()
            pacer.wait()
    except KeyboardInterrupt:
        pass
    final = tracker.finish()
    recorder.events(final)
    for ev in final:
        print(fmt_event(ev), flush=True)
    recorder.close(tracker.rounds, iso_utc(datetime.now(timezone.utc)), result_text(tracker.rounds, human))
    elapsed, rate = pacer.rate()
    kinds = ", ".join(f"{k} {n}" for k, n in sorted(tracker.events.items()))
    unknown = ", ".join(f"{f}=0x{v:X} x{n}" for (f, v), n in st.unknown_codes.items() if isinstance(v, int)) or "none"
    print(f"stopped: {frames} states, {gaps} skipped frames, {skipped_states} states dropped (no valid health), "
          f"{rate:.0f} polls/s over {elapsed:.1f} s, {reader.discarded_health} health reads discarded, "
          f"{reader.torn_rereads} torn re-reads", flush=True)
    print(f"events: {kinds}", flush=True)
    print(f"unknown codes: {unknown}", flush=True)
    print(f"wrote {recorder.recording_path} ({recorder.lines} lines) and {recorder.session_path}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kumite recorder: GameState and events per contracts/recording.md")
    parser.add_argument("--player", required=True)
    parser.add_argument("--bot", required=True, choices=st.CHARACTERS)
    parser.add_argument("--difficulty", type=int, default=1, choices=range(1, 6))
    parser.add_argument("--mode", default="practice", choices=("practice", "versus"))
    parser.add_argument("--stage")
    parser.add_argument("--offsets", default=str(DEFAULT_OFFSETS))
    args = parser.parse_args(argv)

    reader = Reader(args.offsets)
    try:
        if not run_gate(reader, args.offsets):
            return 1
        record(reader, args)
        return 0
    finally:
        reader.close()


if __name__ == "__main__":
    sys.exit(main())
