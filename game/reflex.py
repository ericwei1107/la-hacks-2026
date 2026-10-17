import json
import random
from dataclasses import replace
from pathlib import Path

from game.notation import compile_notation
from game.sequencer import first_press
from game.state import DOWNED_BIT, JUGGLED_BIT, PUNISH_THRESHOLD

ROOT = Path(__file__).resolve().parent.parent
FALLBACK_PATH = Path(__file__).resolve().parent / "punishers_fallback.json"
LOW_LEVELS = ("low", "special_low")
BLOCK_TAIL = 4
THROW_WINDOW = 10
BREAK_PRESS_FRAMES = 3
BREAKS = {"press_1": "1", "press_2": "2", "press_12": "1+2"}
CROUCH_REACTION = 2
SKIP_SHARE = 0.5


def parse_tiers(rows):
    tiers = []
    for row in rows:
        notation = row.get("notation") or row.get("input") or row.get("move")
        startup = row.get("startup")
        if isinstance(startup, str):
            digits = "".join(ch for ch in startup.split("~")[0] if ch.isdigit())
            startup = int(digits) if digits else None
        if notation and isinstance(startup, int):
            tiers.append({"notation": notation, "startup": startup})
    return sorted(tiers, key=lambda t: t["startup"])


def load_punishers(character, root=ROOT, fallback=FALLBACK_PATH):
    path = Path(root) / "characters" / character / "punishers.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if "standing" in data or "crouching" in data:
                table = {"standing": parse_tiers(data.get("standing", [])), "crouching": parse_tiers(data.get("crouching", []))}
            else:
                rows = data.get("punishers", data if isinstance(data, list) else [])
                crouch = [r for r in rows if "ws" in str(r.get("position", r.get("stance", r.get("notation", ""))))]
                stand = [r for r in rows if r not in crouch]
                table = {"standing": parse_tiers(stand), "crouching": parse_tiers(crouch)}
            if table["standing"]:
                return table, path.as_posix()
        except (OSError, ValueError, AttributeError, TypeError):
            pass
    data = json.loads(Path(fallback).read_text(encoding="utf-8"))
    entry = data.get(character, {"standing": [], "crouching": []})
    return {"standing": parse_tiers(entry["standing"]), "crouching": parse_tiers(entry["crouching"])}, "game/punishers_fallback.json"


class Reflex:
    def __init__(self, sequencer, difficulty, latency, punishers, rng=None):
        self.seq = sequencer
        self.difficulty = difficulty
        self.latency = latency
        self.punishers = punishers
        self.rng = rng or random.Random()
        self.handled = None
        self.prev_thrown = "none"
        self.guard = "n"
        self.pending_guard = None
        self.idle_frames = 0
        self.last_frame = None
        self.decisions = []

    def record(self, state, kind, frame_asked, options, chosen, **detail):
        rec = {
            "t": "tactical",
            "session_id": state["session_id"],
            "round": state["round"],
            "frame": state["frame"],
            "frame_asked": frame_asked,
            "options": options,
            "chosen": chosen,
            "probabilities": {o: (1.0 if o == chosen else 0.0) for o in options},
            "source": "reflex",
            "reflex": {"kind": kind, **detail},
        }
        self.decisions.append(rec)
        return rec

    def live(self, state):
        return state["derived"]["situation"] != "round_over" and all(p["health"] > 0 for p in state["players"])

    def reset(self):
        self.handled = None
        self.prev_thrown = "none"
        self.guard = "n"
        self.pending_guard = None
        self.idle_frames = 0

    def step(self, state, events):
        if not self.live(state) or (self.last_frame is not None and state["frame"] < self.last_frame):
            self.reset()
        self.last_frame = state["frame"]
        if not self.live(state):
            return []
        human = state["human_slot"]
        bot_slot = 1 - human
        bot, opp = state["players"][bot_slot], state["players"][human]
        out = []
        out += self._throw_break(state, bot)
        out += self._punish(state, events, bot, bot_slot)
        out += self._block(state, bot, opp)
        self.prev_thrown = bot["being_thrown"]
        return out

    def _press_offset(self, delay):
        return max(0, delay - self.latency)

    def _block(self, state, bot, opp):
        frame = state["frame"]
        out = []
        attacking = opp["hit_level"] not in ("none", "throw") and not opp["free_movement"]
        incapable = bool(bot["status"] & (DOWNED_BIT | JUGGLED_BIT)) or bot["being_thrown"] != "none"
        if incapable:
            self._set_guard("n")
            self.pending_guard = None
            return out
        threat = (opp["move_id"], opp["hit_level"])
        if not attacking:
            self.handled = None
        if attacking and threat != self.handled and self.seq.active is None:
            self.handled = threat
            for move in self.seq.discard(lambda m: m.tag.get("reflex") == "punish", frame):
                out.append(self.record(state, "punish_cancel", frame, [move.notation, "none"], "none",
                                       reason="opponent attacked first", move_id=opp["move_id"]))
            guard = "db" if opp["hit_level"] in LOW_LEVELS else "b"
            if guard == self.guard and self.pending_guard is None:
                delay, at = 0, frame
            else:
                delay = self.difficulty.reaction(self.rng)
                at = frame + self._press_offset(delay)
            self.pending_guard = (guard, at)
            out.append(self.record(state, "block", frame, ["b", "db"], guard, delay=delay, planned_frame=at,
                                   hit_level=opp["hit_level"], move_id=opp["move_id"]))
        if self.pending_guard and frame >= self.pending_guard[1]:
            if attacking:
                self._set_guard(self.pending_guard[0])
            self.pending_guard = None
        if attacking:
            self.idle_frames = 0
        elif self.guard != "n":
            self.idle_frames += 1
            if self.idle_frames >= BLOCK_TAIL:
                self._set_guard("n")
        return out

    def _set_guard(self, guard):
        if guard != self.guard:
            self.guard = guard
            self.seq.hold(guard)

    def _punish(self, state, events, bot, bot_slot):
        out = []
        for ev in events:
            if ev["kind"] != "block" or ev.get("target") != bot_slot or ev.get("frame_advantage") is None:
                continue
            advantage = -ev["frame_advantage"]
            if advantage < PUNISH_THRESHOLD:
                continue
            frame = state["frame"]
            stance = "crouching" if ev.get("detail", {}).get("reaction") == CROUCH_REACTION else "standing"
            timing = replace(self.seq.timing, ws_crouch_frames=0) if stance == "crouching" else self.seq.timing
            tiers = [dict(t, lead=first_press(compile_notation(t["notation"], timing))) for t in self.punishers.get(stance) or []]
            actionable = frame + (0 if bot["free_movement"] else bot["frames_until_actionable"])
            delay = self.difficulty.reaction(self.rng)
            earliest = max(frame, ev["frame"] + self._press_offset(delay))
            for t in tiers:
                t["lateness"] = max(0, earliest - (actionable - self.latency - t["lead"]))
            best = None
            for t in tiers:
                if t["startup"] <= advantage - t["lateness"]:
                    best = t
            choice, miss = best, None
            if best is not None and not self.difficulty.accurate(self.rng):
                slower = next((t for t in tiers if t["startup"] > best["startup"]), None)
                if slower is None or self.rng.random() < SKIP_SHARE:
                    choice, miss = None, "skipped"
                else:
                    choice, miss = slower, "too_slow"
            planned = None
            if choice:
                self.seq.submit(choice["notation"], prepress=True, earliest=earliest, frame=frame, timing=timing, reflex="punish")
                planned = max(earliest, actionable - self.latency - choice["lead"])
            options = [t["notation"] for t in tiers] + ["none"]
            out.append(self.record(state, "punish", ev["frame"], options, choice["notation"] if choice else "none",
                                   advantage=advantage, stance=stance, delay=delay,
                                   lateness=choice["lateness"] if choice else None, planned_frame=planned,
                                   actionable_frame=actionable, startup=choice["startup"] if choice else None,
                                   best=best["notation"] if best else None, rolled_miss=miss,
                                   blocked_move_id=ev.get("move_id")))
        return out

    def _throw_break(self, state, bot):
        code = bot["being_thrown"]
        if code == "none" or self.prev_thrown != "none" or code not in BREAKS:
            return []
        frame = state["frame"]
        delay = self.difficulty.reaction(self.rng)
        offset = max(0, min(delay, THROW_WINDOW) - self.latency)
        press = BREAKS[code]
        miss = None if self.difficulty.accurate(self.rng) else "skipped"
        options = list(BREAKS.values()) + ["none"]
        chosen = "none" if miss else press
        if not miss:
            self.seq.cancel(frame)
            self._set_guard("n")
            timing = replace(self.seq.timing, press_frames=BREAK_PRESS_FRAMES)
            self.seq.submit(press, earliest=frame + offset, frame=frame, force=True, timing=timing, reflex="throw_break")
        return [self.record(state, "throw_break", frame, options, chosen, code=code, delay=delay,
                            planned_frame=frame + offset if not miss else None, window=THROW_WINDOW, rolled_miss=miss)]
