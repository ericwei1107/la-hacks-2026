import copy
import math
from collections import Counter, deque

from game.options import move_key, move_name, step_direction
from game.state import DOWNED_BIT, PUNISH_THRESHOLD, THROW_LIMIT, active
from game.words import AIRBORNE_STATES, state_sentence

AFTER_BLOCK_WINDOW = 20
PRESS_CONFIRM = 12
THROW_PRESS_WINDOW = 20
STEP_WINDOW = 15
TAP_MAX = 3
LATERAL_MM = 120
RETREAT_MM = 150
GUARD_FRAMES = 3
RECENT_EVENTS = 40
LOW_PARRY_SLACK = 3
BREAK_INPUTS = {("1",): "break_1", ("2",): "break_2", ("1", "2"): "break_12"}
ATTACK_BUTTONS = ("1", "2", "3", "4", "heat", "rage")
BUTTON_SLACK = 3
BREAK_CODES = {"press_1": "break_1", "press_2": "break_2", "press_12": "break_12"}
CORRECT_LOW = ("blocked", "low_parry")
CORRECT_PUNISH = ("press", "throw")
CORRECT_SAFE = ("block_high", "backdash", "ss_left", "ss_right")


def in_stun(player):
    return player["hit_reaction"] != 0


def pressed_button(player):
    return any(b in ATTACK_BUTTONS for b in player["buttons_pressed"])


def new_move(subj, prev_subj):
    return not subj["free_movement"] and not in_stun(subj) and (subj["move_id"] != prev_subj["move_id"] or prev_subj["free_movement"])


def self_moved(player):
    return not in_stun(player) and player["being_thrown"] == "none" and not player["status"] & DOWNED_BIT


def lateral_and_forward(start_subject, start_opp, now_subject):
    fx, fz = start_opp["x"] - start_subject["x"], start_opp["z"] - start_subject["z"]
    norm = math.hypot(fx, fz) or 1.0
    fx, fz = fx / norm, fz / norm
    dx, dz = now_subject["x"] - start_subject["x"], now_subject["z"] - start_subject["z"]
    forward = dx * fx + dz * fz
    lateral = fx * dz - fz * dx
    return lateral, forward


class Detector:
    def __init__(self, subject, table=None, recent=RECENT_EVENTS):
        self.subject = subject
        self.opp = 1 - subject
        self.table = table
        self.pending = []
        self.recent = deque(maxlen=recent)
        self.prev = None
        self.last_frame = None
        self.lows = {}
        self.counts = Counter()

    def _name(self, move_id):
        name = move_name(self.table, move_id) if self.table else None
        return move_key(name) if name else f"0x{move_id:x}"

    def _snapshot(self, state):
        return copy.deepcopy(state)

    def _event(self, obs, state, action, correct, **detail):
        start = obs["state"]
        ev = {
            "t": "event",
            "session_id": state["session_id"],
            "frame": state["frame"],
            "round": state["round"],
            "kind": "decision_point",
            "actor": self.subject,
            "target": self.opp,
            "situation": obs["situation"],
            "action": action,
        }
        if obs.get("move_id") is not None:
            ev["move_id"] = obs["move_id"]
        info = {"start_frame": obs["frame"], "correct": bool(correct)}
        info.update({k: v for k, v in detail.items() if v is not None})
        info["state_text"] = state_sentence(start, list(self.recent))
        ev["detail"] = info
        self.counts[(obs["situation"], action)] += 1
        return ev

    def reset(self):
        self.pending = []
        self.recent.clear()
        self.lows = {}
        self.prev = None

    def step(self, state, events):
        frame = state["frame"]
        if self.last_frame is not None and frame < self.last_frame:
            self.reset()
        self.last_frame = frame
        out = []
        subj, opp = state["players"][self.subject], state["players"][self.opp]
        prev = self.prev
        for ev in events:
            out += self._on_event(ev, state, subj, opp, prev)
        if prev is not None:
            out += self._track(state, subj, opp, prev["players"][self.subject], prev["players"][self.opp])
        self._track_lows(state, subj, opp)
        for ev in events + out:
            self.recent.append(ev)
        self.prev = state
        return out

    def _open(self, state, situation, move_id=None, frame=None, **data):
        obs = {"situation": situation, "frame": state["frame"] if frame is None else frame, "state": self._snapshot(state),
               "move_id": move_id, "resolved": False}
        obs.update(data)
        self.pending.append(obs)
        return obs

    def _close(self, obs, state, action, correct, **detail):
        obs["resolved"] = True
        self.pending.remove(obs)
        return self._event(obs, state, action, correct, **detail)

    def _drop_unopened(self):
        for obs in [o for o in self.pending if o["kind"] == "after_block" and o["free_frame"] is None]:
            self.pending.remove(obs)

    def _struck(self, state):
        return [self._close(obs, state, "none", False, evidence="struck") for obs in [o for o in self.pending if o["kind"] == "sidestep_dir"]]

    def _on_event(self, ev, state, subj, opp, prev):
        out = []
        kind = ev["kind"]
        if kind in ("block", "hit", "counter_hit", "throw") and ev.get("target") == self.subject:
            self._drop_unopened()
            out += self._struck(state)
        if kind == "block" and ev.get("actor") == self.opp and ev.get("target") == self.subject and ev.get("frame_advantage") is not None:
            human_adv = -ev["frame_advantage"]
            self._open(state, f"after_block:{self._name(ev['move_id'])}", ev["move_id"], ev["frame"], kind="after_block", adv=human_adv,
                       free_frame=None, dirs=Counter(), tap=None, taps=[], press_at=None, press_move=None, origin=None,
                       last_button=state["frame"] if pressed_button(subj) else None)
        if kind in ("hit", "counter_hit", "block") and ev.get("actor") == self.opp and ev.get("target") == self.subject \
                and ev.get("hit_level") == "low":
            obs = self._open(state, "low_defense", ev["move_id"], ev["frame"], kind="low_defense")
            action = "blocked" if kind == "block" else "hit"
            out.append(self._close(obs, state, action, action in CORRECT_LOW, damage=ev.get("damage"), event=kind))
            self.lows.pop(ev["move_id"], None)
        if kind == "whiff" and ev.get("actor") == self.opp and ev.get("hit_level") == "low":
            info = self.lows.pop(ev["move_id"], None)
            if info and info.get("airborne"):
                obs = self._open(state, "low_defense", ev["move_id"], info["start"], kind="low_defense")
                out.append(self._close(obs, state, "jumped", False, event="whiff"))
        if kind == "hit" and ev.get("actor") == self.subject and subj["hit_level"] == "none":
            for move_id, info in list(self.lows.items()):
                if info.get("active_until") is not None and state["frame"] - info["active_until"] <= LOW_PARRY_SLACK:
                    obs = self._open(state, "low_defense", move_id, kind="low_defense")
                    out.append(self._close(obs, state, "low_parry", True, event="parry", parry_move_id=ev.get("move_id")))
                    self.lows.pop(move_id, None)
                    break
        if kind == "throw" and ev.get("target") == self.subject:
            self._open(state, "throw_break", ev["move_id"], ev["frame"], kind="throw_break", code=(ev.get("detail") or {}).get("break"),
                       pressed=None, health=subj["health"])
        if kind == "throw_break" and ev.get("actor") == self.subject:
            for obs in [o for o in self.pending if o["kind"] == "throw_break"]:
                action = obs["pressed"] or BREAK_CODES.get((ev.get("detail") or {}).get("input"), "none")
                out.append(self._close(obs, state, action, True, code=obs["code"], evidence=(ev.get("detail") or {}).get("evidence")))
        if kind == "throw" and ev.get("actor") == self.subject:
            for obs in [o for o in self.pending if o["kind"] == "after_block"]:
                out.append(self._close(obs, state, "throw", obs["adv"] >= PUNISH_THRESHOLD, adv=obs["adv"]))
        return out

    def _track_lows(self, state, subj, opp):
        if opp["hit_level"] == "low" and not opp["free_movement"]:
            info = self.lows.setdefault(opp["move_id"], {"start": state["frame"], "airborne": False, "active_until": None})
            if subj["basic_state"] in AIRBORNE_STATES:
                info["airborne"] = True
            if active(opp):
                info["active_until"] = state["frame"]
        for move_id in [m for m, info in self.lows.items() if state["frame"] - info["start"] > THROW_LIMIT]:
            self.lows.pop(move_id, None)

    def _tap(self, obs, subj, frame):
        held = subj["dir_held"]
        base = "u" if held in ("u", "uf", "ub") else "d" if held == "d" else "b" if held == "b" else None
        tap = obs.get("tap")
        if tap is not None and base != tap["dir"]:
            if tap["frames"] <= TAP_MAX and held == "n":
                obs["taps"].append(tap)
            obs["tap"] = tap = None
        if base:
            if tap is None:
                obs["tap"] = {"dir": base, "start": frame, "frames": 1}
            else:
                tap["frames"] += 1
        return [t["dir"] for t in obs["taps"] if t["dir"] in ("u", "d")]

    def _track(self, state, subj, opp, prev_subj, prev_opp):
        out = []
        frame = state["frame"]
        if (opp["hit_level"] not in ("none", "throw") and not opp["free_movement"]
                and (prev_opp["hit_level"] == "none" or prev_opp["move_id"] != opp["move_id"])
                and subj["free_movement"] and not subj["status"] & DOWNED_BIT
                and state["derived"]["situation"] in ("neutral", "defense", "pressure")
                and not any(o["kind"] == "sidestep_dir" for o in self.pending)):
            limit = opp["first_active"] if opp["first_active"] > 0 else STEP_WINDOW
            self._open(state, "sidestep_dir", opp["move_id"], kind="sidestep_dir", deadline=frame + min(limit, STEP_WINDOW),
                       tap=None, taps=[], origin=(copy.copy(subj), copy.copy(opp)))
        for obs in list(self.pending):
            if obs["kind"] == "after_block":
                out += self._after_block(obs, state, subj, opp, prev_subj)
            elif obs["kind"] == "sidestep_dir":
                out += self._sidestep(obs, state, subj, opp, prev_subj)
            elif obs["kind"] == "throw_break":
                out += self._throw(obs, state, subj)
        return out

    @staticmethod
    def _rebase(obs, subj, opp, prev_subj):
        if obs.get("origin") is not None and not self_moved(prev_subj) and self_moved(subj):
            obs["origin"] = (copy.copy(subj), copy.copy(opp))

    def _step_label(self, obs, subj, taps):
        if taps:
            return step_direction(taps[0], subj["side"]), "input"
        if not self_moved(subj):
            return None, None
        start_subj, start_opp = obs["origin"]
        lateral, forward = lateral_and_forward(start_subj, start_opp, subj)
        if abs(lateral) >= LATERAL_MM and abs(lateral) > abs(forward):
            return ("right" if lateral > 0 else "left"), "displacement"
        return None, None

    def _is_press(self, obs, subj, prev_subj, frame):
        if not new_move(subj, prev_subj):
            return False
        recent = obs.get("last_button") is not None and frame - obs["last_button"] <= BUTTON_SLACK
        return subj["hit_level"] != "none" or recent

    def _after_block(self, obs, state, subj, opp, prev_subj):
        frame = state["frame"]
        if pressed_button(subj):
            obs["last_button"] = frame
        if obs["free_frame"] is None:
            left_stun = in_stun(prev_subj) and not in_stun(subj) and frame > obs["frame"]
            started = left_stun and self._is_press(obs, subj, prev_subj, frame)
            if subj["free_movement"] or left_stun:
                obs["free_frame"] = frame
                obs["origin"] = (copy.copy(subj), copy.copy(opp))
                if started:
                    obs["press_at"] = frame
                    obs["press_move"] = subj["move_id"]
                    obs["buffered"] = True
            elif frame - obs["frame"] > THROW_LIMIT:
                self.pending.remove(obs)
            if not started:
                return []
        self._rebase(obs, subj, opp, prev_subj)
        taps = self._tap(obs, subj, frame)
        obs["dirs"][subj["dir_held"]] += 1
        if obs["press_at"] is None and self._is_press(obs, subj, prev_subj, frame):
            obs["press_at"] = frame
            obs["press_move"] = subj["move_id"]
        if obs["press_at"] is not None and frame - obs["press_at"] >= PRESS_CONFIRM:
            return [self._close(obs, state, "press", obs["adv"] >= PUNISH_THRESHOLD, adv=obs["adv"], response_move_id=obs["press_move"],
                                buffered=obs.get("buffered"))]
        label, evidence = self._step_label(obs, subj, taps)
        if label and obs["press_at"] is None:
            return [self._close(obs, state, f"ss_{label}", obs["adv"] < PUNISH_THRESHOLD, adv=obs["adv"], evidence=evidence)]
        if obs["press_at"] is None and obs["origin"] is not None:
            _, forward = lateral_and_forward(obs["origin"][0], obs["origin"][1], subj) if self_moved(subj) else (0.0, 0.0)
            backs = [d for d in obs["taps"] if d["dir"] == "b"]
            if forward <= -RETREAT_MM or len(backs) >= 2:
                return [self._close(obs, state, "backdash", obs["adv"] < PUNISH_THRESHOLD, adv=obs["adv"],
                                    evidence="displacement" if forward <= -RETREAT_MM else "input")]
        if frame - obs["free_frame"] >= AFTER_BLOCK_WINDOW and obs["press_at"] is None:
            dirs = obs["dirs"]
            action = "none"
            for direction, label in (("db", "block_low"), ("d", "duck"), ("b", "block_high")):
                if dirs[direction] >= GUARD_FRAMES:
                    action = label
                    break
            if action == "none" and dirs["db"] + dirs["d"] + dirs["b"] >= GUARD_FRAMES:
                action = max((("db", "block_low"), ("d", "duck"), ("b", "block_high")), key=lambda kv: dirs[kv[0]])[1]
            correct = action in CORRECT_SAFE if obs["adv"] < PUNISH_THRESHOLD else action in CORRECT_PUNISH
            return [self._close(obs, state, action, correct, adv=obs["adv"], held=dict(dirs.most_common(3)))]
        return []

    def _sidestep(self, obs, state, subj, opp, prev_subj):
        frame = state["frame"]
        self._rebase(obs, subj, opp, prev_subj)
        taps = self._tap(obs, subj, frame)
        label, evidence = self._step_label(obs, subj, taps)
        if label:
            return [self._close(obs, state, label, True, evidence=evidence)]
        if frame >= obs["deadline"]:
            return [self._close(obs, state, "none", False)]
        return []

    def _throw(self, obs, state, subj):
        frame = state["frame"]
        if obs["pressed"] is None and frame - obs["frame"] <= THROW_PRESS_WINDOW:
            pressed = tuple(sorted(b for b in subj["buttons_pressed"] if b in ("1", "2")))
            if pressed:
                obs["pressed"] = BREAK_INPUTS.get(pressed, "break_12")
        if subj["health"] < obs["health"] or frame - obs["frame"] > THROW_LIMIT:
            return [self._close(obs, state, obs["pressed"] or "none", False, code=obs["code"])]
        return []
