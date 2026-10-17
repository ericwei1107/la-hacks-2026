import json
import math
import random
from dataclasses import replace
from pathlib import Path

from game.notation import compile_notation
from game.sequencer import first_press
from game.state import DOWNED_BIT, JUGGLED_BIT, PUNISH_THRESHOLD, active, lying

ROOT = Path(__file__).resolve().parent.parent
FALLBACK_PATH = Path(__file__).resolve().parent / "punishers_fallback.json"
LOW_LEVELS = ("low", "special_low")
BLOCK_TAIL = 4
THROW_WINDOW = 10
BREAK_PRESS_FRAMES = 3
BREAKS = {"press_1": "1", "press_2": "2", "press_12": "1+2"}
CROUCH_REACTION = 2
SKIP_SHARE = 0.5
PUNISH_REACTION_SCALE = 0.5
WAKEUP_PATH = Path(__file__).resolve().parent / "wakeup_fallback.json"
LYING_STABLE = 2
CLOSE_MM = 1600
MID_MM = 2500
RECOVERING_FRAMES = 15
FACES = {12: "face_up", 13: "face_down"}
WAKEUP_LOGITS = {
    "far": {"stand": 2.0, "forward_roll": 0.8, "back_roll": 0.3, "side_roll": 0.0, "spring_kick": -0.5,
            "rising_low": -2.0, "rising_mid": -2.0},
    "recovering_close": {"rising_mid": 2.0, "rising_low": 1.5, "stand": 0.5, "back_roll": -0.5, "spring_kick": -1.0,
                         "forward_roll": -1.0, "side_roll": -1.0},
    "recovering_mid": {"spring_kick": 1.8, "stand": 1.0, "forward_roll": 0.5, "back_roll": 0.0, "side_roll": -0.5,
                       "rising_mid": -1.0, "rising_low": -1.0},
    "pressure": {"back_roll": 1.6, "side_roll": 1.4, "rising_low": 0.3, "stand": 0.2, "rising_mid": -0.5,
                 "spring_kick": -1.0, "forward_roll": -2.0},
}


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


def load_wakeups(character, path=WAKEUP_PATH):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if character in data:
        return data[character], f"game/{Path(path).name} ({character})"
    return data["kazuya"], f"game/{Path(path).name} (kazuya table, unverified for {character})"


def wakeup_situation(state, bot, opp):
    distance = state["derived"]["distance_mm"]
    recovering = not opp["free_movement"] and opp["frames_until_actionable"] >= RECOVERING_FRAMES and not active(opp)
    if recovering and distance < CLOSE_MM:
        return "recovering_close"
    if recovering and distance < MID_MM:
        return "recovering_mid"
    if distance >= MID_MM:
        return "far"
    return "pressure"


def softmax(logits, temperature):
    top = max(logits.values())
    weights = {k: math.exp((v - top) / temperature) for k, v in logits.items()}
    total = sum(weights.values())
    return {k: w / total for k, w in weights.items()}


class Reflex:
    def __init__(self, sequencer, difficulty, latency, punishers, rng=None, wakeups=None):
        self.seq = sequencer
        self.difficulty = difficulty
        self.latency = latency
        self.punishers = punishers
        self.wakeups = wakeups or {}
        self.rng = rng or random.Random()
        self.lying_run = 0
        self.wake = None
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
        self.lying_run = 0
        self.wake = None
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
        out += self._wakeup(state, bot, opp)
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
            delay = round(self.difficulty.reaction(self.rng) * PUNISH_REACTION_SCALE)
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

    def _wakeup(self, state, bot, opp):
        frame = state["frame"]
        if not bot["status"] & DOWNED_BIT:
            self.lying_run = 0
            self.wake = None
            return []
        ready = lying(bot)
        self.lying_run = self.lying_run + 1 if ready else 0
        if self.wake is not None and self.wake["stage"] == "waiting" and not ready:
            self.wake = None
        if self.wake is None and self.lying_run >= LYING_STABLE:
            delay = self.difficulty.reaction(self.rng)
            self.wake = {"stage": "waiting", "asked": frame, "delay": delay, "at": frame + self._press_offset(delay)}
        if self.wake is None or self.wake["stage"] != "waiting" or frame < self.wake["at"]:
            return []
        face = FACES.get(bot["basic_state"], f"basic_{bot['basic_state']}")
        options = self.wakeups.get(face) or self.wakeups.get("face_up") or []
        if not options:
            self.wake["stage"] = "done"
            return []
        situation = wakeup_situation(state, bot, opp)
        logits = WAKEUP_LOGITS[situation]
        probs = softmax({o["notation"]: logits.get(o["kind"], -2.0) for o in options}, self.difficulty.mixup_temperature)
        pick = self.rng.random()
        chosen = options[-1]
        for o in options:
            pick -= probs[o["notation"]]
            if pick <= 0:
                chosen = o
                break
        self.seq.cancel(frame)
        self._set_guard("n")
        self.seq.submit(chosen["notation"], force=True, frame=frame, reflex="wakeup")
        self.wake["stage"] = "sent"
        rec = self.record(state, "wakeup", self.wake["asked"], [o["notation"] for o in options], chosen["notation"],
                          option=chosen["kind"], situation=situation, delay=self.wake["delay"], face=face,
                          verified=face in self.wakeups, distance=round(state["derived"]["distance_mm"]),
                          opp_move_id=opp["move_id"], opp_actionable_in=opp["frames_until_actionable"])
        rec["probabilities"] = {k: round(v, 4) for k, v in probs.items()}
        return [rec]

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
