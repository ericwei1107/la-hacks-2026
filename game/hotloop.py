import time
from datetime import datetime, timezone

from game import state as st
from game import trace
from game.pacer import Pacer
from game.recorder import Recorder, iso_utc, result_text, session_meta

STALL_S = 2.0
COUNTER_CAP = 0xFFFF
MATCH_OVER = "match_over"
INTERRUPTED = "interrupted"
STOPPED = "stopped"


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
    if "situation" in ev:
        parts.append(f"{ev['situation']} -> {ev.get('action')}")
    if ev.get("detail"):
        parts.append(" ".join(f"{k}={v}" for k, v in ev["detail"].items()
                              if not k.startswith(("attacker_", "defender_")) and k != "state_text"))
    return " ".join(parts)


def fmt_record(rec):
    if rec.get("t") == "event":
        return fmt_event(rec)
    if rec.get("t") == "plan":
        weights = " ".join(f"{k}={v}" for k, v in rec.get("option_weights", {}).items())
        return f"r{rec['round']} f{rec['frame']:>6} plan         {rec.get('note', '')!r} {weights}"
    if rec.get("t") == "learning_event":
        return f"r{rec['round']} f{rec['frame']:>6} learning     {rec.get('event')} {rec.get('situation', '')}"
    if rec.get("t") == "round_summary":
        habits = "; ".join(f"{h['situation']} {h['action']} p={h['p']:.2f} n={h['n']}" for h in rec.get("top_habits", []))
        return (f"r{rec['round']} f{rec.get('frame', 0):>6} summary      winner P{rec['winner'] + 1 if rec.get('winner') is not None else '?'} "
                f"human took {rec['human_damage_taken']}, bot took {rec['bot_damage_taken']}; exploited {rec.get('exploited', [])}; "
                f"fixed {rec.get('newly_fixed', [])}; regressed {rec.get('regressed', [])}; {habits or 'no habits yet'}")
    if rec.get("t") == "tactical" and rec.get("source") != "reflex":
        detail = rec.get("tactical") or {}
        p = rec.get("probabilities", {}).get(rec.get("chosen"))
        extra = " ".join(f"{k}={v}" for k, v in detail.items()
                         if k in ("situation", "distance_bucket", "frame_advantage", "direction", "hit_level") and v is not None)
        return (f"r{rec['round']} f{rec['frame']:>6} {rec.get('source'):<12} {rec.get('chosen')} -> {detail.get('move')} "
                f"p={p} {extra}")
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
    if rf == COUNTER_CAP:
        return (f"round frame counter stuck at its cap {COUNTER_CAP} (about 18 minutes of practice since the last "
                f"position reset). Reset the practice position to restart it; waiting")
    return (f"round frame counter stuck at {rf} for {STALL_S:.0f} s: Tekken is paused (pause menu, or it paused "
            f"because a controller was plugged in or unplugged). Unpause in the game; waiting")


def frames(reader, pacer, on_poll=None, log=print, timer=None):
    prev = None
    last_change = time.monotonic()
    stalled = False
    while True:
        rf = reader.poll_round_frame()
        if rf is not None and rf != prev:
            with trace.decision(timer) as mark:
                with trace.span("read"):
                    snap = reader.snapshot()
                if snap is not None and snap.round_frame != prev:
                    gap = 0 if prev is None or snap.round_frame < prev else snap.round_frame - prev - 1
                    prev = snap.round_frame
                    last_change = time.monotonic()
                    if stalled:
                        log(f"round frame counter moving again at {prev}")
                        stalled = False
                    mark.yielded = True
                    yield snap, gap
                    mark.complete = True
        elif rf is None:
            reader.resolve_blocks()
            reader.resolve_human()
        if not stalled and time.monotonic() - last_change >= STALL_S:
            log(stall_message(rf))
            stalled = True
        if on_poll:
            on_poll()
        pacer.wait()


def round_live(players):
    return all(p["health"] >= p["max_health"] and p["free_movement"] for p in players)


def wait_for_match(reader, pacer, on_poll=None, log=print):
    prev = None
    gap = False
    fresh = False
    while True:
        snap = reader.snapshot()
        if snap is None:
            if not gap:
                log("players not readable: waiting for the next match")
            gap = True
            fresh = True
        else:
            if gap or (prev is not None and snap.round_frame < prev):
                fresh = True
                log(f"new scene at round frame {snap.round_frame}; starting once both players are free at full health")
            gap = False
            prev = snap.round_frame
            if fresh and round_live(snap.players):
                log(f"new match: both players free at full health at round frame {snap.round_frame}")
                return snap
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

    def finish(self, state, events):
        return []

    def close(self):
        pass


def run_session(reader, args, hooks=None, outlet=None):
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
    versus = args.mode == "versus"
    tracker = st.Tracker(sid, timeouts=versus, rounds_to_win=getattr(args, "rounds_to_win", None) if versus else None)
    hooks.start(snap, sid)
    print(f"recording {recorder.recording_path} (human P{human + 1} {human_char} vs {bot_char}); Ctrl+C to stop", flush=True)

    count = 0
    gaps = 0
    skipped_states = 0
    last = None
    reason = STOPPED
    timer = trace.FrameTimer() if getattr(args, "timing", False) else None

    def on_poll():
        recorder.tick()
        hooks.poll()

    loop = frames(reader, pacer, on_poll, timer=timer)

    try:
        for snap, gap in loop:
            gaps += gap
            with trace.span("decode"):
                gs = st.build_state(snap.players, snap.human_slot, snap.round_frame, sid)
                if gs is None:
                    skipped_states += 1
                    continue
                if tracker.match_over and tracker.prev is not None and gs["frame"] < tracker.prev["frame"]:
                    score = "-".join(str(tracker.wins[i]) for i in (human, 1 - human))
                    print(f"match over ({score} for the human): the counter reset into the post-match scene; stopping", flush=True)
                    reason = MATCH_OVER
                    break
                count += 1
                last = gs
                events = tracker.step(gs)
            trace.data(frame=gs["frame"], round=gs["round"])
            extra = hooks.frame(gs, events)
            recorder.events(events)
            recorder.events(extra)
            recorder.state(gs)
            if outlet is not None:
                outlet.state(gs)
                outlet.records(events + extra)
            for rec in events + extra:
                print(fmt_record(rec), flush=True)
            if any(ev["kind"] == "round_end" for ev in events):
                recorder.write_session(tracker.rounds)
    except KeyboardInterrupt:
        reason = INTERRUPTED
    finally:
        loop.close()
        hooks.close()
        final = tracker.finish()
        extra = []
        if final and last is not None:
            try:
                extra = hooks.finish(last, final)
            except Exception as e:
                print(f"finish hook failed: {e!r}", flush=True)
        recorder.events(final)
        recorder.events(extra)
        for rec in final + extra:
            print(fmt_record(rec), flush=True)
        if outlet is not None:
            outlet.records(final + extra)
        recorder.close(tracker.rounds, iso_utc(datetime.now(timezone.utc)), result_text(tracker.rounds, human))
        if outlet is not None and not outlet.close():
            print("coach: a tip was still pending at exit", flush=True)
        elapsed, rate = pacer.rate()
        kinds = ", ".join(f"{k} {n}" for k, n in sorted(tracker.events.items()))
        unknown = ", ".join(f"{f}=0x{v:X} x{n}" for (f, v), n in st.unknown_codes.items() if isinstance(v, int)) or "none"
        print(f"stopped: {count} states, {gaps} skipped frames, {skipped_states} states dropped (no valid health), "
              f"{rate:.0f} polls/s over {elapsed:.1f} s, {reader.discarded_health} health reads discarded, "
              f"{reader.torn_rereads} torn re-reads", flush=True)
        print(f"events: {kinds}", flush=True)
        print(f"unknown codes: {unknown}", flush=True)
        print(f"wrote {recorder.recording_path} ({recorder.lines} lines) and {recorder.session_path}", flush=True)
        if timer is not None:
            print(timer.summary(gaps), flush=True)
    return reason
