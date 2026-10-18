import json
import math
import pickle
import random
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path

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
        "blocked": [("mid", None), ("throw", None)],
        "jumped": [("mid", None)],
        "low_parry": [("mid", None)],
    },
    "after_block": {
        "press": [("mid", None)],
        "duck": [("launcher", None)],
        "block_high": [("low", is_true_low)],
        "block_low": [("mid", None), ("throw", None)],
        "backdash": [("approach", None)],
        "ss_left": [("mid", is_homing), ("launcher", is_homing)],
        "ss_right": [("mid", is_homing), ("launcher", is_homing)],
    },
    "throw_break": {
        "break_1": [("throw", not_broken_by("1"))],
        "break_2": [("throw", not_broken_by("2"))],
        "break_12": [("throw", not_broken_by("1+2"))],
        "none": [("throw", None)],
    },
    "sidestep_dir": {
        "left": [("mid", is_homing), ("launcher", is_homing)],
        "right": [("mid", is_homing), ("launcher", is_homing)],
    },
}


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
        self.last_option = None
        self.pull = None
        self.session_id = None
        self.learning_path = None
        self.round = None
        self.prev_health = None
        self.damage = [0, 0]
        self.moments = []
        self.last_decision = None
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
            self.round = state["round"]
            self.prev_health = None
            self.damage = [0, 0]
            self.moments = []
            self.exploited = set()
            self.newly_fixed = []
            self.regressed = []
            self.player_changed = False
            self.habits.half_life = HALF_LIFE
            self.predictor.reset_round()
            self.pull = None

    def _record(self, state, **fields):
        rec = {"t": "learning_event", "session_id": state["session_id"], "round": state["round"], "frame": state["frame"]}
        rec.update(fields)
        self.events.append(rec)
        return rec

    def step(self, state, events):
        self._begin(state)
        out = []
        human = state["human_slot"]
        healths = [p["health"] for p in state["players"]]
        if self.prev_health is not None:
            for i in (0, 1):
                if healths[i] < self.prev_health[i]:
                    self.damage[1 if i == human else 0] += self.prev_health[i] - healths[i]
        self.prev_health = healths
        for ev in events:
            if ev.get("t") != "event":
                continue
            if ev["kind"] == "decision_point" and ev.get("actor") == human:
                out += self.observe(ev, state)
            elif ev["kind"] in ("hit", "counter_hit", "throw") and ev.get("actor") == 1 - human and ev.get("damage"):
                self._moment(ev)
            self._resolve(ev, state)
        self._expire(state)
        return out

    def _moment(self, ev):
        moment = {"frame": ev["frame"], "kind": ev["kind"], "damage": int(ev.get("damage", 0))}
        if ev.get("move_id") is not None:
            moment["move_id"] = ev["move_id"]
        last = self.last_decision
        if last is not None and last["round"] == ev["round"] and 0 <= ev["frame"] - last["frame"] <= MOMENT_WINDOW:
            moment["situation"] = last["situation"]
        self.moments.append(moment)

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
        hit, changed = self.predictor.observe(features(keys[0], state, self.recent, self.last_option), action)
        if changed:
            self.player_changed = True
            self.habits.half_life = DRIFT_HALF_LIFE
            out.append(self._record(state, event="player_changed", situation=keys[0]))
        self.recent.append(action)
        self.last_decision = {"round": ev["round"], "frame": ev["frame"], "situation": keys[0]}
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
        for key in self.active_keys(state):
            if family(key) in covered:
                continue
            active = self.habits.active(key)
            if active is None:
                continue
            action, p = active
            targets = counters_for(key, action)
            if not targets:
                continue
            covered.add(family(key))
            retest = self.mastery.retest_due(key, round_)
            if self.mastery.fixed(key) and not retest:
                continue
            factor = self.exploit_factor(key)
            for cls, _ in targets:
                if weights is not None and weights.get(cls, 1.0) <= 0:
                    continue
                current = out.get(cls)
                if current is None or factor > current["factor"]:
                    out[cls] = {"factor": round(factor, 3), "situation": key, "action": action, "p": round(p, 3),
                                "n": self.habits.seen[key], "retest": retest}
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
        self.pull = {"key": f"{key}|{action}", "arm": chosen, "frame": None, "round": None, "health": None, "thrown": False}
        return next(e for e in fitting if e["notation"] == chosen)

    def decided(self, chosen, boosts, state):
        self.last_option = chosen
        boost = boosts.get(chosen) if boosts else None
        if boost:
            self.exploited.add(boost["situation"])
            if boost.get("retest"):
                self.mastery.stamp_retest(boost["situation"], state["round"])
        if self.pull is not None and self.pull["frame"] is None:
            if boost:
                human = state["human_slot"]
                self.pull.update(frame=state["frame"], round=state["round"], health=state["players"][human]["health"])
            else:
                self.pull = None

    def _settle(self, reward):
        if self.pull is not None and self.pull["frame"] is not None:
            self.bandit.reward(self.pull["key"], self.pull["arm"], reward)
        self.pull = None

    def _resolve(self, ev, state):
        pull = self.pull
        if pull is None or pull["frame"] is None or ev.get("t") != "event" or ev["round"] != pull["round"]:
            return
        human = state["human_slot"]
        bot = 1 - human
        if ev["frame"] < pull["frame"]:
            return
        if ev.get("actor") == bot and ev["kind"] in ("block", "whiff"):
            self._settle(0.0)
        elif ev.get("actor") == bot and ev["kind"] in ("hit", "counter_hit"):
            self._settle(ev.get("damage", 0) / REWARD_DAMAGE)
        elif ev.get("actor") == bot and ev["kind"] == "throw":
            pull["thrown"] = True
        elif ev["kind"] == "throw_break" and ev.get("target") == bot:
            self._settle(0.0)

    def _expire(self, state):
        pull = self.pull
        if pull is None or pull["frame"] is None:
            return
        human = state["human_slot"]
        if state["round"] != pull["round"] or state["frame"] - pull["frame"] > OUTCOME_WINDOW:
            lost = max(0, pull["health"] - state["players"][human]["health"])
            self._settle(lost / REWARD_DAMAGE)

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
            if active is None or self.mastery.fixed(key):
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
        moments = sorted(self.moments, key=lambda m: -m["damage"])[:MOMENTS]
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
        self._settle_pending(state)
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

    def _settle_pending(self, state):
        pull = self.pull
        if pull is not None and pull["frame"] is not None:
            human = state["human_slot"]
            lost = max(0, pull["health"] - state["players"][human]["health"])
            self._settle(lost / REWARD_DAMAGE)
        self.pull = None

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
