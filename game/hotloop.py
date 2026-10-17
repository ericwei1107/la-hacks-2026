import time
from datetime import datetime, timezone

from game import state as st
from game.pacer import Pacer
from game.recorder import Recorder, iso_utc, result_text, session_meta

STALL_S = 2.0


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


def fmt_record(rec):
    if rec.get("t") == "event":
        return fmt_event(rec)
    detail = rec.get("reflex") or {}
    extra = " ".join(f"{k}=0x{v:04X}" if k.endswith("move_id") and isinstance(v, int) else f"{k}={v}"
                     for k, v in detail.items() if k != "kind" and v is not None)
    return f"r{rec['round']} f{rec['frame']:>6} {rec.get('source', rec['t']):<12} {detail.get('kind', '')} -> {rec.get('chosen')} {extra}"


def wait_snapshot(reader, pacer, on_poll=None):
    while True:
        snap = reader.snapshot()
        if snap is not None:
            return snap
        if on_poll:
            on_poll()
        pacer.wait()


def stall_message(rf):
    if rf is None:
        return "players not readable: waiting for a match or practice"
    return (f"round frame counter stuck at {rf} for {STALL_S:.0f} s: Tekken is paused (pause menu, or it paused "
            f"because a controller was plugged in or unplugged). Unpause in the game; waiting")


def frames(reader, pacer, on_poll=None, log=print):
    prev = None
    last_change = time.monotonic()
    stalled = False
    while True:
        rf = reader.poll_round_frame()
        if rf is not None and rf != prev:
            snap = reader.snapshot()
            if snap is not None and snap.round_frame != prev:
                gap = 0 if prev is None or snap.round_frame < prev else snap.round_frame - prev - 1
                prev = snap.round_frame
                last_change = time.monotonic()
                if stalled:
                    log(f"round frame counter moving again at {prev}")
                    stalled = False
                yield snap, gap
        elif rf is None:
            reader.resolve_blocks()
            reader.resolve_human()
        if not stalled and time.monotonic() - last_change >= STALL_S:
            log(stall_message(rf))
            stalled = True
        if on_poll:
            on_poll()
        pacer.wait()


class Hooks:
    def start(self, snap, sid):
        pass

    def poll(self):
        pass

    def frame(self, state, events):
        return []

    def close(self):
        pass


def run_session(reader, args, hooks=None):
    hooks = hooks or Hooks()
    pacer = Pacer()
    snap = wait_snapshot(reader, pacer, hooks.poll)
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
    hooks.start(snap, sid)
    print(f"recording {recorder.recording_path} (human P{human + 1} {human_char} vs {bot_char}); Ctrl+C to stop", flush=True)

    count = 0
    gaps = 0
    skipped_states = 0

    def on_poll():
        recorder.tick()
        hooks.poll()

    try:
        for snap, gap in frames(reader, pacer, on_poll):
            gaps += gap
            gs = st.build_state(snap.players, snap.human_slot, snap.round_frame, sid)
            if gs is None:
                skipped_states += 1
                continue
            count += 1
            events = tracker.step(gs)
            extra = hooks.frame(gs, events)
            recorder.events(events)
            recorder.events(extra)
            recorder.state(gs)
            for rec in events + extra:
                print(fmt_record(rec), flush=True)
            if any(ev["kind"] == "round_end" for ev in events):
                recorder.write_session(tracker.rounds)
    except KeyboardInterrupt:
        pass
    finally:
        hooks.close()
        final = tracker.finish()
        recorder.events(final)
        for ev in final:
            print(fmt_event(ev), flush=True)
        recorder.close(tracker.rounds, iso_utc(datetime.now(timezone.utc)), result_text(tracker.rounds, human))
        elapsed, rate = pacer.rate()
        kinds = ", ".join(f"{k} {n}" for k, n in sorted(tracker.events.items()))
        unknown = ", ".join(f"{f}=0x{v:X} x{n}" for (f, v), n in st.unknown_codes.items() if isinstance(v, int)) or "none"
        print(f"stopped: {count} states, {gaps} skipped frames, {skipped_states} states dropped (no valid health), "
              f"{rate:.0f} polls/s over {elapsed:.1f} s, {reader.discarded_health} health reads discarded, "
              f"{reader.torn_rereads} torn re-reads", flush=True)
        print(f"events: {kinds}", flush=True)
        print(f"unknown codes: {unknown}", flush=True)
        print(f"wrote {recorder.recording_path} ({recorder.lines} lines) and {recorder.session_path}", flush=True)
