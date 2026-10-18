import math
import random

from game.finetune import laya_prior
from game.options import ATTACK_CLASSES, CLASSES, MOVEMENT_CLASSES, allowed, default_plan, in_range, step_direction
from game.reflex import softmax
from game.state import DOWNED_BIT, JUGGLED_BIT
from game.words import state_sentence

MIN_GAP = 6
PREPRESS_SLACK = 2
DECISION_SITUATIONS = ("neutral", "defense", "knockdown", "wakeup")
NEAR_RULES = {"approach": 0.1, "wait": 0.6, "throw": 1.3, "mid": 1.2, "low": 1.1}
FAR_RULES = {"approach": 2.5, "wait": 1.0, "mid": 0.05, "low": 0.05, "throw": 0.05, "launcher": 0.05, "sidestep": 0.3, "backdash": 0.1}
DISTANCE_RULES = {
    "point_blank": NEAR_RULES,
    "close": NEAR_RULES,
    "mid": {"throw": 0.3, "approach": 0.8, "launcher": 0.8},
    "far": FAR_RULES,
    "very_far": FAR_RULES,
}
PLUS_RULES = {"throw": 1.3, "low": 1.2, "mid": 1.2, "backdash": 0.3, "approach": 0.0, "wait": 0.5}
OKI_RULES = {"mid": 1.3, "low": 1.2, "throw": 0.8, "launcher": 0.0, "sidestep": 0.0}
OUT_OF_RANGE = 0.1
EPS = 1e-9
LAYA_WEIGHT = 0.3


def log_weights(weights):
    return {k: (math.log(w) if w > EPS else -math.inf) for k, w in weights.items()}


def target_keys(targets):
    return sorted((t["situation"], t["action"]) for t in targets)


def boost_targets(boosts):
    return {cls: (b["situation"], b["action"]) for cls, b in boosts.items() if b}


def weighted_choice(rng, items, weights):
    total = sum(weights)
    if total <= 0:
        return rng.choice(items)
    pick = rng.random() * total
    for item, w in zip(items, weights):
        pick -= w
        if pick <= 0:
            return item
    return items[-1]


class Tactical:
    def __init__(self, seq, difficulty, latency, options, rng=None, plan=None, learning=None, laya=None, laya_weight=LAYA_WEIGHT,
                 recent=None):
        self.seq = seq
        self.difficulty = difficulty
        self.latency = latency
        self.options = options
        self.rng = rng or random.Random()
        self.plan = plan or default_plan()
        self.base_note = self.plan.get("note", "")
        self.learning = learning
        self.last_decision = None
        self.last_frame = None
        self.plan_logged = False
        self.decisions = []
        self.last_option = None
        self.laya = laya
        self.laya_weight = laya_weight
        self.recent = recent
        self.texts = []
        self.laya_stats = {"decisions": 0, "answered": 0, "changed": 0}

    def ask_laya(self, state, reflex):
        if self.laya is None:
            return
        if not reflex.live(state) or state["derived"]["situation"] not in DECISION_SITUATIONS:
            self.texts = []
            return
        text = state_sentence(state, list(self.recent()) if self.recent else None)
        self.texts = [(state["round"], state["frame"], text)] + [t for t in self.texts[:1] if t[0] == state["round"] and t[1] == state["frame"] - 1]
        self.laya.submit(text)

    def laya_answer(self):
        for round_, frame, text in self.texts:
            answers = self.laya.answer(text)
            if answers is not None:
                return frame, answers
        return None, None

    def plan_record(self, state):
        rec = {"t": "plan", "session_id": state["session_id"], "round": state["round"], "frame": state["frame"]}
        rec.update(self.plan)
        return rec

    def set_plan(self, plan):
        self.plan = plan
        self.base_note = plan.get("note", "")
        self.plan_logged = False

    def eligible(self, state, reflex):
        human = state["human_slot"]
        bot = state["players"][1 - human]
        if not reflex.live(state) or reflex.pending(state) or self.seq.busy():
            return False
        if bot["status"] & (DOWNED_BIT | JUGGLED_BIT) or bot["being_thrown"] != "none":
            return False
        if state["derived"]["situation"] not in DECISION_SITUATIONS:
            return False
        if not (bot["free_movement"] or bot["frames_until_actionable"] <= self.latency + PREPRESS_SLACK):
            return False
        if self.last_decision is not None and state["frame"] - self.last_decision < MIN_GAP:
            return False
        return True

    def class_weights(self, state):
        derived = state["derived"]
        bucket = derived["distance_bucket"]
        human = state["players"][state["human_slot"]]
        weights = {}
        for cls in CLASSES:
            w = float(self.plan["option_weights"].get(cls, 0.0))
            w *= DISTANCE_RULES.get(bucket, {}).get(cls, 1.0)
            if derived["situation"] == "defense" and derived["frame_advantage"] is not None and derived["frame_advantage"] < 0:
                w *= PLUS_RULES.get(cls, 1.0)
            if human["status"] & DOWNED_BIT:
                w *= OKI_RULES.get(cls, 1.0)
            entries = self.candidates(cls, bucket)
            if not entries:
                w = 0.0
            elif not any(in_range(e, bucket) for e in entries):
                w *= OUT_OF_RANGE
            weights[cls] = w
        return weights

    def candidates(self, cls, bucket=None):
        return [e for e in self.options["classes"].get(cls, []) if allowed(e, self.difficulty)]

    def pick_entry(self, cls, bucket, boosts):
        entries = self.candidates(cls, bucket)
        fitting = [e for e in entries if in_range(e, bucket)] or entries
        if self.learning is not None and boosts.get(cls):
            chosen = self.learning.pick(cls, fitting, boosts[cls], self.difficulty, self.rng)
            if chosen is not None:
                return chosen
        return weighted_choice(self.rng, fitting, [float(e.get("weight", 1.0)) for e in fitting])

    def step(self, state, events, reflex):
        out = []
        frame = state["frame"]
        if self.last_frame is not None and frame < self.last_frame:
            self.last_decision = None
        self.last_frame = frame
        if self.learning is not None:
            targets = self.learning.targets()
            current = self.plan.get("target_habits", [])
            if target_keys(targets) != target_keys(current):
                self.plan = {**self.plan, "target_habits": targets, "note": self.learning.note(targets, self.base_note)}
                self.plan_logged = False
            elif targets != current:
                self.plan = {**self.plan, "target_habits": targets}
        if not self.plan_logged and reflex.live(state):
            self.plan_logged = True
            out.append(self.plan_record(state))
        self.ask_laya(state, reflex)
        if not self.eligible(state, reflex):
            return out
        human = state["human_slot"]
        bot = state["players"][1 - human]
        bucket = state["derived"]["distance_bucket"]
        weights = self.class_weights(state)
        boosts = self.learning.boosts(state, weights) if self.learning is not None else {}
        asked, answers, laya_detail = frame, None, None
        if self.laya is not None:
            self.laya_stats["decisions"] += 1
            asked, answers = self.laya_answer()
            if answers is None:
                asked = frame
                laya_detail = {"ready": False}
            else:
                prior = laya_prior(answers)
                habit = boosts
                if self.learning is not None:
                    boosts = self.learning.boosts(state, weights, prior, self.laya_weight)
                changed = boost_targets(boosts) != boost_targets(habit)
                self.laya_stats["answered"] += 1
                self.laya_stats["changed"] += changed
                laya_detail = {
                    "ready": True,
                    "version": self.laya.version,
                    "weight": self.laya_weight,
                    "p": {q: None if a.get("p") is None else round(a["p"], 4) for q, a in answers.items()},
                    "prediction": {fam: {"action": max(dist, key=dist.get), "p": round(max(dist.values()), 4)} for fam, dist in prior.items()},
                    "changed": changed,
                }
                if changed:
                    laya_detail["habit_boosts"] = {c: f"{b['situation']} {b['action']}" for c, b in habit.items() if b}
        boosted = {cls: w * boosts.get(cls, {}).get("factor", 1.0) for cls, w in weights.items()} if boosts else dict(weights)
        if all(w <= EPS for w in boosted.values()):
            boosted["wait"] = 1.0
        probs = softmax(log_weights(boosted), self.difficulty.mixup_temperature)
        chosen = weighted_choice(self.rng, list(probs), list(probs.values()))
        entry = self.pick_entry(chosen, bucket, boosts)
        notation = entry["notation"]
        prepress = not bot["free_movement"]
        move = self.seq.submit(notation, prepress=True, frame=frame, tactical=chosen)
        self.last_decision = frame
        self.last_option = chosen
        if self.learning is not None:
            self.learning.decided(chosen, boosts, state, move)
        source = "laya" if answers is not None else ("habit" if boosts.get(chosen) else "default")
        detail = {
            "move": notation,
            "situation": state["derived"]["situation"],
            "distance_bucket": bucket,
            "distance_mm": round(state["derived"]["distance_mm"]),
            "frame_advantage": state["derived"]["frame_advantage"],
            "weights": {c: round(w, 4) for c, w in boosted.items()},
            "prepress": prepress,
        }
        if chosen == "sidestep":
            detail["direction"] = step_direction(notation, bot["side"])
        if chosen in ATTACK_CLASSES:
            detail["hit_level"] = entry.get("hit_level")
            detail["move_id"] = entry.get("move_id")
        if boosts:
            detail["boosts"] = {c: b for c, b in boosts.items() if b}
        if laya_detail is not None:
            detail["laya"] = laya_detail
        rec = {
            "t": "tactical",
            "session_id": state["session_id"],
            "round": state["round"],
            "frame": frame,
            "frame_asked": asked,
            "options": list(CLASSES),
            "chosen": chosen,
            "probabilities": {c: round(p, 4) for c, p in probs.items()},
            "source": source,
            "tactical": detail,
        }
        self.decisions.append(rec)
        out.append(rec)
        return out


def is_movement(move):
    return move is not None and move.tag.get("tactical") in MOVEMENT_CLASSES
