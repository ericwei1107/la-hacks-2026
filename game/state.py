import math
from collections import Counter

NONE_CODE = 0xC000001D
THROW_CODES = {0xC000001D: "none", 0xD000001C: "press_1", 0xE000001F: "press_2", 0xF000001E: "press_12"}
HIT_LEVELS = ("none", "high", "mid", "low", "special_low", "throw")
CHARACTERS = ("devil_jin", "kazuya", "king", "shaheen")
CHARACTER_SHORT = {"devil_jin": "djin", "kazuya": "kaz", "king": "king", "shaheen": "shaheen"}
DIRECTIONS = {1: "n", 2: "db", 4: "d", 8: "df", 16: "b", 32: "n", 64: "f", 128: "ub", 256: "u", 512: "uf"}
BUTTON_BITS = (("1", 0), ("2", 1), ("3", 2), ("4", 3), ("heat", 4), ("rage", 6))
PRESSED_SHIFT = 0
HELD_SHIFT = 9
HEAT_FULL = 23039456
ESCAPE_BIT = 0x800
DOWNED_BIT = 0x80
JUGGLED_BIT = 0x400
JUGGLED_STATE = 14
REACTIONS = {1: "block", 2: "block", 3: "hit", 10: "counter_hit", 11: "counter_hit", 12: "hit", 13: "hit"}
DISTANCE_BUCKETS = ((1100, "point_blank"), (1600, "close"), (2500, "mid"), (3500, "far"))
FPS = 60
ROUND_SECONDS = 60
CONNECT_DELAY = 2
WAKEUP_WINDOW = 30
PUNISH_THRESHOLD = 10

unknown_codes = Counter()


def rol32(value, bits):
    value &= 0xFFFFFFFF
    return ((value << bits) | (value >> (32 - bits))) & 0xFFFFFFFF


def heat_fraction(value):
    if value == NONE_CODE:
        return 0.0
    return round(min(1.0, max(0.0, rol32(value, 8) / HEAT_FULL)), 4)


def buttons(word, shift):
    return [name for name, bit in BUTTON_BITS if word >> (shift + bit) & 1]


def closed(value, allowed, field, fallback):
    if value in allowed:
        return value
    unknown_codes[(field, value)] += 1
    return fallback


def build_player(index, raw):
    for name in ("health", "recoverable_limit", "max_health"):
        if raw.get(name) is None:
            return None
    x, y, z = raw["position"]
    free = bool(raw["free_movement"])
    total = raw["move_total"]
    frame = raw["frame_in_move"]
    level = raw.get("hit_level_name")
    if level is None:
        unknown_codes[("hit_level", raw["hit_level"])] += 1
        level = "none"
    return {
        "slot": closed(raw["slot"], (0, 1), "slot", index),
        "character_id": raw["character_id"],
        "character": closed(raw.get("character"), CHARACTERS, "character", "unknown"),
        "health": raw["health"],
        "recoverable_limit": raw["recoverable_limit"],
        "max_health": raw["max_health"],
        "x": round(x, 1),
        "y": round(y, 1),
        "z": round(z, 1),
        "facing": raw["facing"],
        "side": closed(raw["side"], (0, 1), "side", 0),
        "move_id": raw["move_id"],
        "frame_in_move": frame,
        "move_total": total,
        "free_movement": free,
        "hit_level": level,
        "hit_reaction": raw["hit_reaction"],
        "status": raw["status"],
        "basic_state": raw["basic_state"],
        "being_thrown": THROW_CODES.get(raw["being_thrown"]) or closed(raw["being_thrown"], (), "being_thrown", "none"),
        "throw_escaped": bool(raw["throw_escape_flags"] & ESCAPE_BIT),
        "heat_gauge": heat_fraction(raw["heat_gauge"]),
        "heat_active": bool(raw["heat_active"]),
        "heat_used": bool(raw["heat_used"]),
        "rage_active": bool(raw["rage_active"]),
        "power_crush": bool(raw["power_crush"]),
        "first_active": raw.get("first_active", 0),
        "last_active": raw.get("last_active", 0),
        "first_airborne": raw.get("first_airborne", 0),
        "last_airborne": raw.get("last_airborne", 0),
        "dir_held": DIRECTIONS.get(raw["dir_held"]) or closed(raw["dir_held"], (), "dir_held", "n"),
        "buttons_held": buttons(raw["game_buttons"], HELD_SHIFT),
        "buttons_pressed": buttons(raw["game_buttons"], PRESSED_SHIFT),
        "frames_until_actionable": 0 if free else max(0, total - frame),
    }


def distance_bucket(distance):
    for limit, name in DISTANCE_BUCKETS:
        if distance < limit:
            return name
    return "very_far"


def derive(players, human_slot, frame):
    h, o = players[human_slot], players[1 - human_slot]
    dx, dz = o["x"] - h["x"], o["z"] - h["z"]
    distance = math.hypot(dx, dz)
    return {
        "distance_mm": round(distance, 1),
        "distance_bucket": distance_bucket(distance),
        "frame_advantage": None,
        "situation": "neutral",
        "bearing_deg": round(math.degrees(math.atan2(dx, dz)) % 360.0, 1),
        "timer_s": round(max(0.0, ROUND_SECONDS - frame / FPS), 2),
    }


def build_state(raw_players, human_slot, frame, session_id):
    players = [build_player(i, raw) for i, raw in enumerate(raw_players)]
    if any(p is None for p in players):
        return None
    return {
        "t": "state",
        "session_id": session_id,
        "frame": frame,
        "round": 1,
        "human_slot": human_slot,
        "players": players,
        "derived": derive(players, human_slot, frame),
    }


def advantage(attacker, defender):
    return (defender["move_total"] - defender["frame_in_move"]) - (attacker["move_total"] - attacker["frame_in_move"])


class Tracker:
    def __init__(self, session_id):
        self.session_id = session_id
        self.round = 0
        self.prev = None
        self.rounds = []
        self.events = Counter()
        self._reset_round(None)

    def _reset_round(self, frame):
        self.round_start = frame
        self.ko = False
        self.pending = []
        self.adv = None
        self.actions = [None, None]
        self.down_cleared = [None, None]

    def event(self, kind, frame, round_=None, **fields):
        self.events[kind] += 1
        ev = {"t": "event", "session_id": self.session_id, "frame": frame, "round": round_ or self.round, "kind": kind}
        ev.update({k: v for k, v in fields.items() if v is not None or k == "frame_advantage"})
        return ev

    def _end_round(self, frame, winner, reason, out):
        self.rounds.append({"round": self.round, "winner": winner, "start_frame": self.round_start, "end_frame": frame})
        out.append(self.event("round_end", frame, detail={"reason": reason, "winner": winner}))

    def _start_round(self, frame, reason, out):
        self.round += 1
        self._reset_round(frame)
        out.append(self.event("round_start", frame, detail={"reason": reason}))

    def step(self, state):
        out = []
        frame = state["frame"]
        players = state["players"]
        prev = self.prev
        same = prev
        if prev is None:
            self._start_round(frame, "session_start", out)
        elif frame < prev["frame"]:
            if not self.ko:
                self._end_round(prev["frame"], None, "counter_reset", out)
            self._start_round(frame, "counter_reset", out)
            same = None
        state["round"] = self.round
        if prev is not None and [p["side"] for p in players] != [p["side"] for p in prev["players"]]:
            out.append(self.event("side_switch", frame, detail={"sides": [p["side"] for p in players]}))
        connected = [False, False]
        struck = [False, False]
        if same is not None:
            self._connections(state, same, connected, struck, out)
            self._throws(state, same, connected, struck, out)
            self._knockdowns(state, same, out)
            self._ko(state, same, out)
        self._resolve_pending(state, out)
        self._whiffs(state, connected, struck, out)
        if all(p["free_movement"] for p in players) and not self.pending:
            self.adv = None
        state["derived"]["frame_advantage"] = self.adv
        state["derived"]["situation"] = self.situation(state)
        self.prev = state
        return out

    def _connections(self, state, prev, connected, struck, out):
        for a in (0, 1):
            d = 1 - a
            att = state["players"][a]
            if att["hit_reaction"] and not prev["players"][a]["hit_reaction"]:
                self.pending.append({
                    "attacker": a,
                    "frame": state["frame"],
                    "code": att["hit_reaction"],
                    "move_id": att["move_id"],
                    "hit_level": att["hit_level"],
                    "health_before": prev["players"][d]["health"],
                })
                connected[a] = True
                struck[d] = True

    def _resolve_pending(self, state, out):
        players = state["players"]
        human = state["human_slot"]
        keep = []
        for p in self.pending:
            if state["frame"] - p["frame"] < CONNECT_DELAY:
                keep.append(p)
                continue
            a, d = p["attacker"], 1 - p["attacker"]
            att, dfn = players[a], players[d]
            adv = advantage(att, dfn)
            self.adv = adv if a == human else -adv
            out.append(self.event(
                REACTIONS.get(p["code"], "hit"),
                p["frame"],
                actor=a,
                target=d,
                move_id=p["move_id"],
                hit_level=p["hit_level"],
                frame_advantage=adv,
                damage=max(0, p["health_before"] - dfn["health"]),
                detail={
                    "reaction": p["code"],
                    "read_frame": state["frame"],
                    "attacker_move_id": att["move_id"],
                    "attacker_total": att["move_total"],
                    "attacker_frame": att["frame_in_move"],
                    "defender_move_id": dfn["move_id"],
                    "defender_total": dfn["move_total"],
                    "defender_frame": dfn["frame_in_move"],
                },
            ))
        self.pending = keep

    def _throws(self, state, prev, connected, struck, out):
        for d in (0, 1):
            a = 1 - d
            cur, old = state["players"][d], prev["players"][d]
            if cur["being_thrown"] != "none" and old["being_thrown"] == "none":
                out.append(self.event(
                    "throw",
                    state["frame"],
                    actor=a,
                    target=d,
                    move_id=state["players"][a]["move_id"],
                    hit_level="throw",
                    detail={"break": cur["being_thrown"]},
                ))
                connected[a] = True
                struck[d] = True
            if cur["throw_escaped"] and not old["throw_escaped"] and (cur["being_thrown"] != "none" or old["being_thrown"] != "none"):
                out.append(self.event(
                    "throw_break",
                    state["frame"],
                    actor=d,
                    target=a,
                    move_id=state["players"][a]["move_id"],
                    detail={"input": cur["being_thrown"]},
                ))

    def _knockdowns(self, state, prev, out):
        for d in (0, 1):
            cur, old = state["players"][d], prev["players"][d]
            down, was_down = bool(cur["status"] & DOWNED_BIT), bool(old["status"] & DOWNED_BIT)
            if down and not was_down:
                cause = "throw" if cur["being_thrown"] != "none" else "hit"
                out.append(self.event("knockdown", state["frame"], actor=1 - d, target=d, detail={"cause": cause}))
            if was_down and not down:
                self.down_cleared[d] = state["frame"]

    def _ko(self, state, prev, out):
        if self.ko:
            return
        dead = [p["health"] <= 0 for p in state["players"]]
        if any(dead) and not any(p["health"] <= 0 for p in prev["players"]):
            self.ko = True
            winner = None if all(dead) else dead.index(False)
            self._end_round(state["frame"], winner, "ko", out)

    def _whiffs(self, state, connected, struck, out):
        for i, p in enumerate(state["players"]):
            act = self.actions[i]
            if act is None and not p["free_movement"]:
                act = self.actions[i] = {"move_id": None, "hit_level": None, "frame": None, "connected": False, "struck": False}
            if act is None:
                continue
            if p["hit_level"] != "none" and act["hit_level"] is None:
                act.update(move_id=p["move_id"], hit_level=p["hit_level"], frame=state["frame"])
            act["connected"] |= connected[i]
            act["struck"] |= struck[i] or p["being_thrown"] != "none"
            if p["free_movement"]:
                if act["hit_level"] and not act["connected"] and not act["struck"]:
                    out.append(self.event(
                        "whiff",
                        state["frame"],
                        actor=i,
                        move_id=act["move_id"],
                        hit_level=act["hit_level"],
                        detail={"start_frame": act["frame"]},
                    ))
                self.actions[i] = None

    def situation(self, state):
        players = state["players"]
        frame = state["frame"]
        if self.ko:
            return "round_over"
        if any(p["being_thrown"] != "none" for p in players):
            return "throw"
        if any(p["status"] & JUGGLED_BIT or p["basic_state"] == JUGGLED_STATE for p in players):
            return "combo"
        if any(p["status"] & DOWNED_BIT for p in players):
            return "knockdown"
        for i, p in enumerate(players):
            cleared = self.down_cleared[i]
            if cleared is not None and frame - cleared <= WAKEUP_WINDOW and not p["free_movement"]:
                return "wakeup"
        if self.adv is None:
            return "neutral"
        if self.adv >= PUNISH_THRESHOLD:
            return "punish_window"
        if self.adv > 0:
            return "pressure"
        if self.adv < 0:
            return "defense"
        return "neutral"

    def finish(self):
        out = []
        if self.prev is not None and not self.ko:
            self._end_round(self.prev["frame"], None, "stop", out)
            self.ko = True
        return out


def session_id(started, player, human_character, bot_character):
    stamp = started.strftime("%Y-%m-%dT%H-%M-%S")
    return f"{stamp}_{player}_{CHARACTER_SHORT.get(human_character, 'unknown')}_vs_{CHARACTER_SHORT.get(bot_character, 'unknown')}"
