import json
import math
import pickle
import random
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path

from game.options import ATTACK_CLASSES
from game.recorder import data_dir, dumps, iso_utc
from game.reflex import softmax
from game.words import ACTION_WORDS, frame_words, lead_words, timer_words

try:
    from river import forest
except ImportError:
    forest = None

HALF_LIFE = 20
DRIFT_HALF_LIFE = 10
ACTIVE_N = 4
ACTIVE_P = 0.6
NEW_SESSION_SCALE = 0.5
BKT = {"l0": 0.2, "t": 0.15, "g": 0.2, "s": 0.1, "f": 0.02}
P_MAX = 0.98
P_MIN = 0.02
FIXED_P = 0.85
FIXED_N = 6
REGRESS_P = 0.5
RETEST_ROUNDS = 2
DISCOUNT = 0.9
REWARD_DAMAGE = 25
OUTCOME_WINDOW = 90
GAIN = 3.0
TARGET_RATE = 0.5
MIN_SCALE = 0.5
TOP_HABITS = 3
MOMENTS = 3
MOMENT_WINDOW = 90
RECENT_ACTIONS = 3
PREDICTOR_TREES = 10
AFTER_BLOCK = "after_block:"
PLUS_KEY = "after_block:bot_plus"
MINUS_KEY = "after_block:bot_minus"
ANY_KEY = "after_block:any"
ALWAYS_KEYS = ("low_defense", "throw_break", "sidestep_dir")
NOTE_LIMIT = 80


def is_true_low(entry):
    return entry.get("hit_level") == "low"


def is_homing(entry):
    return "homing" in entry.get("tags", [])


def is_mid(entry):
    return entry.get("hit_level") in ("mid", "special_mid")


def is_homing_mid(entry):
    return is_homing(entry) and is_mid(entry)


def move_int(value):
    if isinstance(value, str):
        try:
            return int(value, 16)
        except ValueError:
            return None
    return value


def entry_ids(entry):
    ids = {move_int(i) for i in (entry.get("move_ids") or [])}
    ids.add(move_int(entry.get("move_id")))
    return {i for i in ids if i is not None}


def break_codes(text):
    if not text:
        return set()
    return {part.strip() for part in str(text).replace(",", "/").split("/") if part.strip()}


def not_broken_by(press):
    def check(entry):
        codes = break_codes(entry.get("break"))
        return bool(codes) and press not in codes
    return check


COUNTERS = {
    "low_defense": {
        "hit": [("low", is_true_low)],
        "blocked": [("mid", is_mid), ("throw", None)],
        "jumped": [("mid", is_mid)],
        "low_parry": [("mid", is_mid)],
    },
    "after_block": {
        "press": [("mid", None)],
        "duck": [("launcher", is_mid), ("mid", is_mid)],
        "block_high": [("low", is_true_low)],
        "block_low": [("mid", is_mid), ("throw", None)],
        "backdash": [("approach", None)],
        "ss_left": [("mid", is_homing_mid), ("launcher", is_homing_mid)],
        "ss_right": [("mid", is_homing_mid), ("launcher", is_homing_mid)],
    },
    "throw_break": {
        "break_1": [("throw", not_broken_by("1"))],
        "break_2": [("throw", not_broken_by("2"))],
        "break_12": [("throw", not_broken_by("1+2"))],
        "none": [("throw", None)],
    },
    "sidestep_dir": {
        "left": [("mid", is_homing_mid), ("launcher", is_homing_mid)],
        "right": [("mid", is_homing_mid), ("launcher", is_homing_mid)],
    },
}
STATE_HISTORY = 240
MAX_PULLS = 4
THROW_START = 30
THROW_CLEAR = 5
THROW_LIMIT_FRAMES = 180
CONNECT_LAG = 2
START_SLACK = 4
INPUT_IDS = {0x53, 0x58, 0x5A, 0x5B, 0x5A7, 0x5C1, 0x5C2, 0x5C6, 0x5C7, 0x5C8, 0x5DB, 0x5DC, 0x5DD, 0x6F2, 0x6F4, 0x6F5, 0x6F7, 0x6F8,
             0x90E, 0x914, 0x915}


def family(key):
    return "after_block" if key.startswith(AFTER_BLOCK) else key


def counters_for(key, action):
    return COUNTERS.get(family(key), {}).get(action, [])


def learner_keys(situation, detail):
    if not situation.startswith(AFTER_BLOCK):
        return [situation], None
    adv = (detail or {}).get("adv")
    pooled = MINUS_KEY if adv is not None and adv > 0 else PLUS_KEY
    return [pooled, ANY_KEY], situation


def bkt_update(p, correct, params=BKT):
    g, s, t = params["g"], params["s"], params["t"]
    if correct:
        cond = p * (1 - s) / max(p * (1 - s) + (1 - p) * g, 1e-9)
    else:
        cond = p * s / max(p * s + (1 - p) * (1 - g), 1e-9)
    return min(P_MAX, max(P_MIN, cond + (1 - cond) * t))


class Habits:
    def __init__(self, counts=None, rates=None):
        self.counts = {sit: {a: [float(v[0]), float(v[1])] for a, v in row.items()} for sit, row in (counts or {}).items()}
        self.rates = {sit: [float(v[0]), float(v[1])] for sit, v in (rates or {}).items()}
        self.seen = Counter({sit: int(round(self.n(sit))) for sit in self.counts})
        self.half_life = HALF_LIFE

    def decay(self):
        return 0.5 ** (1.0 / self.half_life)

    def scale(self, factor):
        for row in self.counts.values():
            for arm in row.values():
                arm[0] *= factor
        for rate in self.rates.values():
            rate[0] *= factor
            rate[1] *= factor
        self.seen = Counter({sit: int(round(self.n(sit))) for sit in self.counts})

    def observe(self, situation, action, correct):
        row = self.counts.setdefault(situation, {})
        d = self.decay()
        for arm in row.values():
            arm[0] *= d
        row.setdefault(action, [0.0, 1.0])[0] += 1.0
        rate = self.rates.setdefault(situation, [0.0, 0.0])
        rate[0] = rate[0] * d + (1.0 if correct else 0.0)
        rate[1] = rate[1] * d + 1.0
        self.seen[situation] += 1

    def n(self, situation):
        return sum(arm[0] for arm in self.counts.get(situation, {}).values())

    def p(self, situation, action):
        row = self.counts.get(situation, {})
        s, prior = row.get(action, [0.0, 1.0])
        return (s + prior) / (self.n(situation) + prior + 1.0)

    def correct_rate(self, situation):
        c, n = self.rates.get(situation, [0.0, 0.0])
        return c / n if n > 0 else None

    def top(self, situation):
        row = self.counts.get(situation, {})
        if not row:
            return None, 0.0
        action = max(row, key=lambda a: self.p(situation, a))
        return action, self.p(situation, action)

    def active(self, situation):
        action, p = self.top(situation)
        if action is None or self.seen[situation] < ACTIVE_N or p < ACTIVE_P:
            return None
        return action, p

    def snapshot(self):
        return {sit: {a: [round(v[0], 4), v[1]] for a, v in row.items()} for sit, row in self.counts.items()}


class Mastery:
    def __init__(self, data=None):
        self.skills = {}
        for key, row in (data or {}).items():
            self.skills[key] = {"p_learned": float(row.get("p_learned", BKT["l0"])), "observations": int(row.get("observations", 0)),
                                "fixed": bool(row.get("fixed", False)), "last_retest": row.get("last_retest")}
        self.retest_round = {}

    def skill(self, key):
        return self.skills.setdefault(key, {"p_learned": BKT["l0"], "observations": 0, "fixed": False, "last_retest": None})

    def observe(self, key, correct):
        row = self.skill(key)
        row["p_learned"] = bkt_update(row["p_learned"], correct)
        row["observations"] += 1
        if not row["fixed"] and row["p_learned"] >= FIXED_P and row["observations"] >= FIXED_N:
            row["fixed"] = True
            return "fixed"
        if row["fixed"] and row["p_learned"] <= REGRESS_P:
            row["fixed"] = False
            return "regressed"
        return None

    def forget(self):
        for row in self.skills.values():
            row["p_learned"] = max(0.0, row["p_learned"] * (1 - BKT["f"]))

    def p(self, key):
        return self.skills[key]["p_learned"] if key in self.skills else None

    def fixed(self, key):
        return bool(self.skills.get(key, {}).get("fixed"))

    def retest_due(self, key, round_):
        if not self.fixed(key):
            return False
        last = self.retest_round.get(key)
        return last is None or round_ - last >= RETEST_ROUNDS

    def stamp_retest(self, key, round_):
        self.retest_round[key] = round_
        self.skill(key)["last_retest"] = iso_utc(datetime.now(timezone.utc))

    def snapshot(self):
        return {k: {"p_learned": round(v["p_learned"], 4), "observations": v["observations"], "fixed": v["fixed"],
                    "last_retest": v["last_retest"]} for k, v in self.skills.items()}


class Bandit:
    def __init__(self, data=None):
        self.arms = {key: {arm: [float(v[0]), float(v[1])] for arm, v in row.items()} for key, row in (data or {}).items()}
        self.switches = 0
        self.last_pick = {}

    def pull(self, key, arms, temperature, rng):
        if not arms:
            return None
        row = self.arms.setdefault(key, {})
        for arm in row.values():
            arm[0] *= DISCOUNT
            arm[1] *= DISCOUNT
        samples = {}
        for arm in arms:
            s, f = row.setdefault(arm, [0.0, 0.0])
            samples[arm] = rng.betavariate(s + 1.0, f + 1.0)
        probs = softmax({a: math.log(max(v, 1e-9)) for a, v in samples.items()}, temperature)
        pick = rng.random()
        chosen = arms[-1]
        for arm, p in probs.items():
            pick -= p
            if pick <= 0:
                chosen = arm
                break
        if key in self.last_pick and self.last_pick[key] != chosen:
            self.switches += 1
        self.last_pick[key] = chosen
        return chosen

    def reward(self, key, arm, value):
        value = min(1.0, max(0.0, float(value)))
        row = self.arms.setdefault(key, {}).setdefault(arm, [0.0, 0.0])
        row[0] += value
        row[1] += 1.0 - value

    def rate(self, key, arm):
        s, f = self.arms.get(key, {}).get(arm, [0.0, 0.0])
        return (s + 1.0) / (s + f + 2.0)

    def rates(self):
        return {key: {arm: round(self.rate(key, arm), 4) for arm in row} for key, row in self.arms.items() if row}

    def snapshot(self):
        return {key: {arm: [round(v[0], 4), round(v[1], 4)] for arm, v in row.items()} for key, row in self.arms.items()}


class Predictor:
    def __init__(self, model=None, seed=0):
        if model is None and forest is not None:
            model = forest.ARFClassifier(n_models=PREDICTOR_TREES, seed=seed)
        self.model = model
        self.drifts = model.n_drifts_detected() if model is not None else 0
        self.correct = 0
        self.total = 0
        self.seen = 0

    @property
    def enabled(self):
        return self.model is not None

    def observe(self, features, label):
        if self.model is None:
            return False, False
        hit = None
        if self.seen > 0:
            probs = self.model.predict_proba_one(features)
            if probs:
                guess = max(probs, key=probs.get)
                hit = guess == label
                self.total += 1
                self.correct += int(hit)
        self.model.learn_one(features, label)
        self.seen += 1
        drifts = self.model.n_drifts_detected()
        changed = drifts > self.drifts
        self.drifts = drifts
        return hit, changed

    def accuracy(self):
        return self.correct / self.total if self.total else None

    def reset_round(self):
        self.correct = 0
        self.total = 0

    def save(self, path):
        if self.model is None:
            return False
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(self.model, fh)
        return True

    @classmethod
    def load(cls, path, seed=0):
        try:
            with open(path, "rb") as fh:
                return cls(pickle.load(fh), seed)
        except (OSError, pickle.PickleError, AttributeError, EOFError, ImportError):
            return cls(None if forest is None else forest.ARFClassifier(n_models=PREDICTOR_TREES, seed=seed), seed)


def features(key, state, recent, last_option):
    human = state["human_slot"]
    h, b = state["players"][human], state["players"][1 - human]
    derived = state["derived"]
    out = {
        "situation": key,
        "distance": derived.get("distance_bucket", "mid"),
        "frames": frame_words(derived.get("frame_advantage")) or "none",
        "timer": timer_words(derived.get("timer_s")) or "none",
        "lead": lead_words(h, b),
        "wall": "open",
        "bot_option": last_option or "none",
    }
    acts = list(recent)[-RECENT_ACTIONS:]
    for i in range(RECENT_ACTIONS):
        out[f"last{i + 1}"] = acts[-1 - i] if i < len(acts) else "none"
    return out


class Learning:
    def __init__(self, player, character, options, difficulty, rng=None, root=None, predictor=True, profile=None):
        self.player = player
        self.character = character
        self.options = options
        self.difficulty = difficulty
        self.rng = rng or random.Random()
        self.root = Path(root) if root else data_dir()
        self.profile_path = self.root / "profiles" / f"{player}_{character}.json"
        self.predictor_path = self.profile_path.with_name(f"{player}_{character}.predictor.pkl")
        data = profile if profile is not None else self.read_profile()
        self.sessions = int(data.get("sessions", 0)) + 1
        self.history = list(data.get("history", []))
        self.habits = Habits(data.get("habits"), (data.get("rates") or {}))
        self.habits.scale(NEW_SESSION_SCALE)
        self.mastery = Mastery(data.get("mastery"))
        self.mastery.forget()
        self.bandit = Bandit(data.get("bandits"))
        seed = self.rng.randrange(1 << 30)
        self.predictor = Predictor.load(self.predictor_path, seed) if predictor else Predictor(None)
        self.recent = deque(maxlen=RECENT_ACTIONS)
        self.states = deque(maxlen=STATE_HISTORY)
        self.last_option = None
        self.pulls = []
        self.next_pull = None
        self.learned_ids = {}
        self.prev_bot_reacting = False
        self.prev_bot_move = None
        self.session_id = None
        self.learning_path = None
        self.round = None
        self.prev_health = None
        self.damage = [0, 0]
        self.moments = []
        self.throw_moments = []
        self.decisions = deque(maxlen=8)
        self.exploited = set()
        self.newly_fixed = []
        self.regressed = []
        self.player_changed = False
        self.detected_round = {}
        self.fixed_round = {}
        self.rounds = []
        self.events = []
        self.observations = 0

    def read_profile(self):
        try:
            data = json.loads(self.profile_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def profile(self):
        return {
            "player": self.player,
            "character": self.character,
            "sessions": self.sessions,
            "habits": self.habits.snapshot(),
            "mastery": self.mastery.snapshot(),
            "bandits": self.bandit.snapshot(),
            "predictor": self.predictor_path.relative_to(self.root).as_posix() if self.predictor.enabled else None,
            "history": self.history[-20:],
            "rates": {k: [round(v[0], 4), round(v[1], 4)] for k, v in self.habits.rates.items()},
        }

    def save(self):
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.profile_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.profile(), indent=2), encoding="utf-8")
        tmp.replace(self.profile_path)
        self.predictor.save(self.predictor_path)
        return self.profile_path

    def _begin(self, state):
        if self.session_id != state["session_id"]:
            self.session_id = state["session_id"]
            self.learning_path = self.root / "learning" / f"{self.session_id}.jsonl"
        if self.round != state["round"]:
            if self.prev_health is not None:
                self._settle_pending(self.prev_health[state["human_slot"]])
            self.round = state["round"]
            self.prev_health = None
            self.damage = [0, 0]
            self.moments = []
            self.throw_moments = []
            self.decisions.clear()
            self.exploited = set()
            self.newly_fixed = []
            self.regressed = []
            self.player_changed = False
            self.habits.half_life = HALF_LIFE
            self.predictor.reset_round()
            self.pulls = []
            self.next_pull = None

    def _record(self, state, **fields):
        rec = {"t": "learning_event", "session_id": state["session_id"], "round": state["round"], "frame": state["frame"]}
        rec.update(fields)
        self.events.append(rec)
        return rec

    def _closing_state(self, state, ev):
        if ev["round"] == state["round"]:
            return state
        stub = dict(state, round=ev["round"], frame=ev["frame"])
        if self.prev_health is not None:
            stub["players"] = [dict(p, health=h) for p, h in zip(state["players"], self.prev_health)]
        return stub

    def step(self, state, events):
        out = []
        ends = [ev for ev in events if ev.get("t") == "event" and ev.get("kind") == "round_end"]
        for ev in ends:
            if ev["round"] != state["round"] and self.round == ev["round"]:
                out += self.round_end(self._closing_state(state, ev), ev)
        self._begin(state)
        self.states.append(state)
        human = state["human_slot"]
        healths = [p["health"] for p in state["players"]]
        if self.prev_health is not None:
            for i in (0, 1):
                if healths[i] < self.prev_health[i]:
                    self.damage[1 if i == human else 0] += self.prev_health[i] - healths[i]
        self.prev_health = healths
        self._track_bot_move(state)
        ordered = sorted((ev for ev in events if ev.get("t") == "event"), key=lambda e: e.get("kind") != "decision_point")
        for ev in ordered:
            if ev["kind"] == "decision_point" and ev.get("actor") == human:
                out += self.observe(ev, state)
            elif ev["kind"] in ("hit", "counter_hit") and ev.get("actor") == 1 - human and ev.get("damage"):
                self._close_throw_moments(ev, state)
                self._moment(ev)
            elif ev["kind"] == "throw" and ev.get("actor") == 1 - human:
                self._throw_moment(ev, state)
            elif ev["kind"] == "throw_break" and ev.get("target") == 1 - human:
                self._cancel_throw_moments(ev)
            self._resolve(ev, state)
        self._update_throw_moments(state)
        self._expire(state)
        for ev in ends:
            if ev["round"] == state["round"]:
                out += self.round_end(state, ev)
        return out

    def _state_at(self, round_, frame):
        if frame is None:
            return None
        for s in reversed(self.states):
            if s["round"] == round_ and s["frame"] == frame:
                return s
            if s["round"] < round_ or (s["round"] == round_ and s["frame"] < frame):
                break
        return None

    def _situation_for(self, ev):
        for d in reversed(self.decisions):
            if d["round"] == ev["round"] and d["start_frame"] is not None and abs(d["start_frame"] - ev["frame"]) <= 2:
                return d["situation"], True
        for d in reversed(self.decisions):
            if d["round"] == ev["round"] and 0 <= ev["frame"] - d["frame"] <= MOMENT_WINDOW:
                return d["situation"], False
        return None, False

    def _moment(self, ev):
        moment = {"frame": ev["frame"], "kind": ev["kind"], "damage": int(ev.get("damage", 0))}
        if ev.get("move_id") is not None:
            moment["move_id"] = ev["move_id"]
        situation, exact = self._situation_for(ev)
        if situation:
            moment["situation"] = situation
        moment["_exact"] = exact
        self.moments.append(moment)
        return moment

    def _throw_moment(self, ev, state):
        human = state["human_slot"]
        moment = self._moment(dict(ev, damage=0))
        self.throw_moments.append({"moment": moment, "health": state["players"][human]["health"], "frame": ev["frame"], "round": ev["round"],
                                   "thrown": False, "clear": 0})

    def _cancel_throw_moments(self, ev):
        for pending in [t for t in self.throw_moments if t["round"] == ev["round"] and 0 <= ev["frame"] - t["frame"] <= THROW_LIMIT_FRAMES]:
            if pending["moment"] in self.moments:
                self.moments.remove(pending["moment"])
            self.throw_moments.remove(pending)

    def _close_throw_moments(self, ev, state):
        human_health = state["players"][state["human_slot"]]["health"]
        for pending in self.throw_moments:
            pending["moment"]["damage"] = max(0, pending["health"] - human_health - int(ev.get("damage", 0)))
        self.throw_moments = []

    def _update_throw_moments(self, state):
        human = state["human_slot"]
        thrown_now = state["players"][human]["being_thrown"] != "none"
        for pending in list(self.throw_moments):
            age = state["frame"] - pending["frame"]
            if pending["round"] != state["round"] or age > THROW_LIMIT_FRAMES or (not pending["thrown"] and age > THROW_START):
                self.throw_moments.remove(pending)
                continue
            if not pending["thrown"] or thrown_now or pending["clear"] < THROW_CLEAR:
                pending["moment"]["damage"] = max(0, pending["health"] - state["players"][human]["health"])
            if thrown_now:
                pending["thrown"] = True
                pending["clear"] = 0
            elif pending["thrown"]:
                pending["clear"] += 1
                if pending["clear"] >= THROW_CLEAR + CONNECT_LAG:
                    self.throw_moments.remove(pending)

    def _attribute(self, decision):
        for moment in self.moments:
            if not moment["_exact"] and decision["start_frame"] is not None and abs(moment["frame"] - decision["start_frame"]) <= 2:
                moment["situation"] = decision["situation"]
                moment["_exact"] = True

    def observe(self, ev, state):
        out = []
        detail = ev.get("detail") or {}
        action = ev["action"]
        correct = bool(detail.get("correct"))
        keys, detail_key = learner_keys(ev["situation"], detail)
        self.observations += 1
        for key in keys + ([detail_key] if detail_key else []):
            self.habits.observe(key, action, correct)
            if key not in self.detected_round and self.habits.active(key):
                self.detected_round[key] = state["round"]
        for key in keys:
            change = self.mastery.observe(key, correct)
            if change == "fixed":
                self.newly_fixed.append(key)
                self.fixed_round.setdefault(key, state["round"])
                out.append(self._record(state, event="fixed", situation=key, mastery=round(self.mastery.p(key), 3)))
            elif change == "regressed":
                self.regressed.append(key)
                out.append(self._record(state, event="regressed", situation=key, mastery=round(self.mastery.p(key), 3)))
        start = self._state_at(ev["round"], detail.get("start_frame")) or state
        hit, changed = self.predictor.observe(features(keys[0], start, self.recent, self.last_option), action)
        if changed:
            self.player_changed = True
            self.habits.half_life = DRIFT_HALF_LIFE
            out.append(self._record(state, event="player_changed", situation=keys[0]))
        self.recent.append(action)
        decision = {"round": ev["round"], "frame": ev["frame"], "start_frame": detail.get("start_frame"), "situation": detail_key or keys[0]}
        self.decisions.append(decision)
        self._attribute(decision)
        return out

    def active_keys(self, state):
        derived = state["derived"]
        keys = list(ALWAYS_KEYS)
        adv = derived.get("frame_advantage")
        if derived.get("situation") == "defense" or (adv is not None and adv < 0):
            keys.append(PLUS_KEY)
            keys.append(ANY_KEY)
        return keys

    def exploit_factor(self, key):
        r = self.habits.correct_rate(key)
        scale = 1.0 if r is None else max(MIN_SCALE, min(1.0, r / TARGET_RATE))
        return 1.0 + GAIN * self.difficulty.exploit_weight * scale

    def boosts(self, state, weights=None):
        out = {}
        round_ = state["round"]
        covered = set()
        retests = set()
        for key in self.active_keys(state):
            if family(key) in covered:
                continue
            retest = self.mastery.retest_due(key, round_)
            if self.mastery.fixed(key) and not retest:
                covered.add(family(key))
                continue
            if retest:
                retests.add(key)
            active = self.habits.active(key)
            if active is None:
                continue
            action, p = active
            targets = counters_for(key, action)
            if not targets:
                continue
            covered.add(family(key))
            factor = self.exploit_factor(key)
            for cls, _ in targets:
                if weights is not None and weights.get(cls, 1.0) <= 0:
                    continue
                current = out.get(cls)
                if current is None or factor > current["factor"]:
                    out[cls] = {"factor": round(factor, 3), "situation": key, "action": action, "p": round(p, 3),
                                "n": self.habits.seen[key], "retest": retest or (key == ANY_KEY and PLUS_KEY in retests)}
        return out

    def pick(self, cls, entries, boost, difficulty, rng=None):
        rng = rng or self.rng
        key, action = boost["situation"], boost["action"]
        filters = [f for c, f in counters_for(key, action) if c == cls]
        fitting = [e for e in entries if any(f is None or f(e) for f in filters)] if filters else []
        if not fitting:
            return None
        arms = [e["notation"] for e in fitting]
        chosen = self.bandit.pull(f"{key}|{action}", arms, difficulty.mixup_temperature, rng)
        entry = next(e for e in fitting if e["notation"] == chosen)
        ids = entry_ids(entry) | self.learned_ids.get(chosen, set())
        self.next_pull = {"key": f"{key}|{action}", "arm": chosen, "cls": cls, "entry": entry, "ids": ids, "start_ids": ids - INPUT_IDS,
                          "frame": None, "round": None, "health": None, "started": False, "start_frame": None, "base_move": None,
                          "busy": False, "lapsed": False, "thrown": False, "move": None}
        return entry

    @property
    def pull(self):
        return self.pulls[-1] if self.pulls else None

    def decided(self, chosen, boosts, state, move=None):
        self.last_option = chosen
        boost = boosts.get(chosen) if boosts else None
        human = state["human_slot"]
        if boost:
            self.exploited.add(boost["situation"])
            if boost.get("retest"):
                self.mastery.stamp_retest(boost["situation"], state["round"])
                if boost["situation"] == ANY_KEY and self.mastery.retest_due(PLUS_KEY, state["round"]):
                    self.mastery.stamp_retest(PLUS_KEY, state["round"])
        if boost and self.next_pull is not None:
            pull = self.next_pull
            pull.update(frame=state["frame"], round=state["round"], health=state["players"][human]["health"], move=move,
                        base_move=state["players"][1 - human]["move_id"])
            if move is None and not pull["ids"]:
                self._start(pull, state)
            while len(self.pulls) >= MAX_PULLS:
                self._settle(self.pulls[0], self._final_reward(self.pulls[0], state["players"][human]["health"]))
            self.pulls.append(pull)
        self.next_pull = None

    def _start(self, pull, state):
        bot = state["players"][1 - state["human_slot"]]
        pull["started"] = True
        pull["start_frame"] = state["frame"]
        if pull["base_move"] is None:
            pull["base_move"] = bot["move_id"]
        pull["health"] = state["players"][state["human_slot"]]["health"]

    def _settle(self, pull, reward):
        if pull in self.pulls:
            self.pulls.remove(pull)
        if reward is not None:
            self.bandit.reward(pull["key"], pull["arm"], reward)

    def _final_reward(self, pull, human_health):
        if not pull["started"]:
            return None
        if pull["ids"] and not pull["thrown"]:
            return 0.0
        return max(0, pull["health"] - human_health) / REWARD_DAMAGE

    def _learn_id(self, pull, bot, frame):
        if pull["cls"] not in ATTACK_CLASSES or not pull["started"] or pull["move"] is None or pull["lapsed"]:
            return
        move = pull["move"]
        over = move.cancelled or (move.done_frame is not None and frame > move.done_frame + START_SLACK)
        if (over and not pull["busy"]) or (pull["busy"] and (bot["free_movement"] or bot["hit_reaction"] != 0)):
            pull["lapsed"] = True
            pull["lapsed_at"] = frame
            pull["busy"] = False
            if not pull["ids"]:
                self._settle(pull, None)
            return
        if bot["free_movement"] or bot["hit_reaction"] != 0:
            pull["busy"] = False
            return
        if bot["move_id"] == pull["base_move"] or bot["hit_level"] == "none" or bot["move_id"] in INPUT_IDS:
            return
        if bot["move_id"] in pull["ids"]:
            pull["busy"] = True
            return
        if any(bot["move_id"] in other["ids"] for other in self.pulls if other is not pull):
            return
        if not pull["busy"] and pull["ids"] and entry_ids(pull["entry"]):
            return
        pull["ids"].add(bot["move_id"])
        pull["busy"] = True
        self.learned_ids.setdefault(pull["arm"], set()).add(bot["move_id"])
        entry = pull.get("entry")
        if entry is not None:
            entry["move_ids"] = sorted(set(entry.get("move_ids") or []) | {f"0x{bot['move_id']:x}"})

    def _track_bot_move(self, state):
        bot = state["players"][1 - state["human_slot"]]
        reacting = bot["hit_reaction"] != 0 and not bot["free_movement"]
        restarted = self.prev_bot_move is not None and (bot["move_id"] != self.prev_bot_move[0] or bot["frame_in_move"] < self.prev_bot_move[1])
        struck = reacting and (not self.prev_bot_reacting or restarted)
        self.prev_bot_reacting = bot["hit_reaction"] != 0
        self.prev_bot_move = (bot["move_id"], bot["frame_in_move"])
        for pull in list(self.pulls):
            if state["round"] != pull["round"] or state["frame"] < pull["frame"]:
                continue
            move = pull["move"]
            if move is not None:
                if move.cancelled and move.start_frame is None:
                    self._settle(pull, None)
                    continue
                if not pull["started"] and move.start_frame is not None:
                    self._start(pull, state)
            elif not pull["started"] and bot["move_id"] in pull["start_ids"]:
                self._start(pull, state)
            if pull["started"] and pull["cls"] in ATTACK_CLASSES and not pull["thrown"] and struck and state["frame"] > pull["start_frame"]:
                self._settle(pull, 0.0)
                continue
            self._learn_id(pull, bot, state["frame"])

    def _resolve(self, ev, state):
        if ev.get("t") != "event":
            return
        bot = 1 - state["human_slot"]
        for pull in list(self.pulls):
            if ev["round"] != pull["round"] or ev["frame"] < pull["frame"] or not pull["ids"]:
                continue
            if pull["lapsed"] and ev["frame"] > pull["lapsed_at"]:
                continue
            if not pull["started"]:
                if pull["move"] is None and ev.get("actor") == bot and ev.get("move_id") in pull["ids"]:
                    self._start(pull, state)
                    pull["start_frame"] = pull["frame"]
                else:
                    continue
            began = (ev.get("detail") or {}).get("start_frame")
            if ev["frame"] < pull["start_frame"] or (began is not None and began < pull["start_frame"]):
                continue
            if ev.get("actor") == bot and ev.get("move_id") in pull["ids"]:
                if ev["kind"] in ("block", "whiff"):
                    self._settle(pull, 0.0)
                elif ev["kind"] in ("hit", "counter_hit"):
                    self._settle(pull, ev.get("damage", 0) / REWARD_DAMAGE)
                elif ev["kind"] == "throw":
                    pull["thrown"] = True
                return
            if ev["kind"] == "throw_break" and ev.get("target") == bot and pull["thrown"]:
                self._settle(pull, 0.0)
                return

    def _expire(self, state):
        human_health = state["players"][state["human_slot"]]["health"]
        for pull in list(self.pulls):
            limit = THROW_LIMIT_FRAMES if pull["thrown"] else OUTCOME_WINDOW
            if state["round"] != pull["round"] or state["frame"] - pull["frame"] > limit:
                self._settle(pull, self._final_reward(pull, human_health))

    def habit_rows(self, keys=None):
        rows = {}
        for key in sorted(keys if keys is not None else self.habits.counts):
            action, p = self.habits.top(key)
            if action is None:
                continue
            rows[key] = {"action": action, "p": round(p, 4), "n": int(self.habits.seen[key]),
                         "mastery": round(self.mastery.p(key) if self.mastery.p(key) is not None else BKT["l0"], 4),
                         "fixed": self.mastery.fixed(key)}
        return rows

    def pooled_keys(self):
        return [k for k in self.habits.counts if not k.startswith(AFTER_BLOCK) or k in (PLUS_KEY, MINUS_KEY, ANY_KEY)]

    def top_habits(self):
        rows = self.habit_rows(self.pooled_keys())
        ranked = sorted(rows.items(), key=lambda kv: (kv[1]["n"] >= ACTIVE_N and kv[1]["p"] >= ACTIVE_P, kv[1]["n"], kv[1]["p"]), reverse=True)
        return [{"situation": k, "action": r["action"], "p": r["p"], "n": r["n"], "mastery": r["mastery"], "fixed": r["fixed"]}
                for k, r in ranked[:TOP_HABITS]]

    def targets(self):
        out = []
        for key in self.pooled_keys():
            active = self.habits.active(key)
            if key == MINUS_KEY or active is None or self.mastery.fixed(key):
                continue
            action, p = active
            if counters_for(key, action):
                out.append({"situation": key, "action": action, "weight": round(min(1.0, p), 2)})
        return out

    def note(self, targets):
        if not targets:
            return "Kazuya defaults"
        top = max(targets, key=lambda t: t["weight"])
        words = ACTION_WORDS.get(top["action"], top["action"].replace("_", " "))
        return f"You {words} {top['weight']:.0%} of the time"[:NOTE_LIMIT]

    def round_record(self, state):
        return {
            "t": "learning_round",
            "session_id": state["session_id"],
            "round": state["round"],
            "frame": state["frame"],
            "prediction_accuracy": None if self.predictor.accuracy() is None else round(self.predictor.accuracy(), 4),
            "habits": self.habit_rows(self.pooled_keys()),
            "bandit": self.bandit.rates(),
            "player_changed": self.player_changed,
        }

    def summary(self, state, winner):
        human = state["human_slot"]
        moments = sorted((m for m in self.moments if m["damage"] > 0), key=lambda m: -m["damage"])[:MOMENTS]
        moments = [{k: v for k, v in m.items() if not k.startswith("_")} for m in moments]
        return {
            "t": "round_summary",
            "session_id": state["session_id"],
            "round": state["round"],
            "frame": state["frame"],
            "winner": winner,
            "human_slot": human,
            "human_character": state["players"][human]["character"],
            "bot_character": state["players"][1 - human]["character"],
            "difficulty": self.difficulty.level,
            "human_damage_taken": int(self.damage[1]),
            "bot_damage_taken": int(self.damage[0]),
            "top_habits": self.top_habits(),
            "biggest_moments": sorted(moments, key=lambda m: m["frame"]),
            "exploited": sorted(self.exploited),
            "newly_fixed": list(self.newly_fixed),
            "regressed": list(self.regressed),
        }

    def round_end(self, state, ev=None):
        self._begin(state)
        self._settle_pending(state["players"][state["human_slot"]]["health"])
        winner = (ev.get("detail") or {}).get("winner") if ev else None
        round_rec = self.round_record(state)
        self.rounds.append(round_rec)
        self.learning_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.learning_path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(dumps(round_rec) + "\n")
        summary = self.summary(state, winner)
        self.mastery.forget()
        self.history = self.history[-19:] + [{"session_id": state["session_id"], "round": state["round"], "winner": winner,
                                              "observations": self.observations}]
        self.save()
        self.round = None
        return [summary]

    def _settle_pending(self, human_health):
        for pull in list(self.pulls):
            self._settle(pull, self._final_reward(pull, human_health))
        self.pulls = []

    def status(self):
        parts = []
        for key in self.pooled_keys():
            active = self.habits.active(key)
            if active is None:
                continue
            action, p = active
            m = self.mastery.p(key)
            parts.append(f"{key} {action} p={p:.2f} n={self.habits.seen[key]} mastery={m if m is None else round(m, 2)}"
                         + (" fixed" if self.mastery.fixed(key) else ""))
        acc = self.predictor.accuracy()
        head = f"accuracy {acc:.0%}" if acc is not None else "accuracy n/a"
        return head + (": " + "; ".join(parts) if parts else ": no active habits")

    def metrics(self):
        return {
            "session_id": self.session_id or "",
            "rounds": [{k: v for k, v in r.items() if k != "frame"} for r in self.rounds],
            "time_to_detect": dict(self.detected_round),
            "time_to_mastery": dict(self.fixed_round),
            "finetune": {"before": None, "after": None},
        }
