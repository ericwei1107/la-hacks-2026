import json
import random
from pathlib import Path

from game.combos import (CAPTURED_DIR, COUNTER_HIT_REACTIONS, OPENER_HIT_WINDOW, ROUTES_PATH, ComboRunner, connect_signal,
                         distance, load_routes)
from game.notation import compile_notation
from game.state import JUGGLED_BIT, REACTIONS

FULL_SHARE = {"short": 0.0, "short_plus_optimal": 0.5, "optimal": 1.0}
NONE = "none"
NO_LAUNCH = "no_launch"
ROUND_OVER = "round over"
LAUNCHER_WINDOW = 60
LAUNCH_WINDOW = 30
FULL_SOURCES = ("punish", "combo")


def hex_id(value):
    return int(value, 16) if isinstance(value, str) else value


def short_ids(route):
    first = route["segments"][0]["hits"][0]
    return {hex_id(v) for v in route.get("launcher_move_ids") or [first.get("move_id")] if v is not None}


def full_ids(route):
    hits = route.get("hits") or []
    ids = {hex_id(route.get("launcher_move_id"))} | ({hex_id(hits[0][2])} if hits else set())
    ids |= {r["move_id"] for r in route.get("frames") or [] if 0 <= r.get("offset", -1) <= OPENER_HIT_WINDOW}
    return ids - {None}


def press_signature(frames):
    out = []
    for i, (direction, buttons) in enumerate(frames):
        if buttons and (i == 0 or tuple(frames[i - 1]) != (direction, tuple(buttons))):
            out.append((direction, tuple(sorted(buttons))))
    return out


def launcher_signature(route):
    if route.get("captured"):
        events = sorted(route.get("launcher_inputs") or [], key=lambda e: e[0])
        return [(direction, tuple(sorted(buttons))) for _, direction, buttons, _ in events if buttons]
    return press_signature(compile_notation(route["launcher"]))


def move_source(move):
    if move.tag.get("combo"):
        return "combo"
    if move.tag.get("reflex"):
        return move.tag["reflex"]
    if move.tag.get("tactical"):
        return f"tactical:{move.tag['tactical']}"
    return "other"


def launched(route, target, counter_hit):
    return counter_hit if needs_counter_hit(route) else bool(target["status"] & JUGGLED_BIT)


def needs_counter_hit(route):
    return bool(route.get("counter_hit")) or route.get("requires") == "counter_hit"


def fits(route, ids, move_id, counter_hit, heat):
    return move_id in ids and (counter_hit or not needs_counter_hit(route)) and (heat or not route.get("heat"))


def load_play_routes(character, routes_path=ROUTES_PATH, captured_dir=CAPTURED_DIR):
    data = load_routes(routes_path)
    if data.get("character") != character:
        return {}, {}
    short = {name: r for name, r in data["routes"].items() if not r.get("experimental")}
    full = {}
    for path in sorted(Path(captured_dir).glob("*.json")):
        route = json.loads(path.read_text(encoding="utf-8"))
        if route.get("captured") and not route.get("experimental"):
            full[route["name"]] = route
    return short, full


def landed(prev_target, target):
    return connect_signal(prev_target, target) and REACTIONS.get(target["hit_reaction"]) != "block"


def progress(runner):
    if runner.captured:
        return min(len(runner.hits), runner.planned_hits), runner.planned_hits
    return len(runner.connects), len(runner.links)


def route_names(routes):
    return " ".join(sorted(routes, key=lambda n: (len(n), n))) or NONE


def describe(short, full, difficulty):
    share = FULL_SHARE.get(difficulty.combo_set, 0.0)
    return (f"combos ({difficulty.combo_set}: full route {share:.0%} of the time when one fits): "
            f"short {route_names(short)}; full {route_names(full)}")


class ComboPlay:
    def __init__(self, seq, difficulty, rng=None, routes=None):
        self.seq = seq
        self.difficulty = difficulty
        self.rng = rng or random.Random()
        self.short, self.full = routes if routes is not None else ({}, {})
        self.short_ids = {name: short_ids(r) for name, r in self.short.items()}
        self.full_ids = {name: full_ids(r) for name, r in self.full.items()}
        self.short_sig = {name: launcher_signature(r) for name, r in self.short.items()}
        self.full_sig = {name: launcher_signature(r) for name, r in self.full.items()}
        self.runner = None
        self.pending = None
        self.attempt = None
        self.prev = None
        self.last_move = None
        self.handled = None
        self.decisions = []

    def busy(self):
        return self.runner is not None or self.pending is not None

    def share(self):
        return FULL_SHARE.get(self.difficulty.combo_set, 0.0)

    def candidates(self, move_id, counter_hit, heat, move):
        if move is None:
            return [], []
        signature = press_signature(move.frames)
        short = [n for n, r in self.short.items()
                 if fits(r, self.short_ids[n], move_id, counter_hit, heat) and signature == self.short_sig[n]]
        full = [n for n, r in self.full.items()
                if fits(r, self.full_ids[n], move_id, counter_hit, heat) and signature == self.full_sig[n]
                and move_source(move) in FULL_SOURCES]
        short.sort(key=lambda n: -self.short[n].get("listed_damage", 0))
        full.sort(key=lambda n: -self.full[n].get("damage", 0))
        return short, full

    def choose(self, short, full):
        p_full = self.share() if full else 0.0
        p_short = 1.0 - p_full if short else 0.0
        probs = {n: 0.0 for n in full + short}
        if full:
            probs[full[0]] = p_full
        if short:
            probs[short[0]] = p_short
        probs[NONE] = round(1.0 - p_full - p_short, 4)
        weighted = [(n, p) for n, p in probs.items() if p > 0]
        if len(weighted) == 1:
            return weighted[0][0], probs
        pick = self.rng.random()
        for name, p in weighted:
            pick -= p
            if pick <= 0:
                return name, probs
        return weighted[-1][0], probs

    def step(self, state, live):
        frame = state["frame"]
        bot_slot = 1 - state["human_slot"]
        prev = self.prev
        self.prev = state
        if prev is not None and frame < prev["frame"]:
            prev = None
            self.last_move = None
            self.handled = None
        active = self.seq.active
        if active is not None and self.runner is None and self.pending is None:
            self.last_move = active
        if self.pending is not None:
            return self.arm(state, live, bot_slot)
        if self.runner is not None:
            return self.advance(state, live, bot_slot)
        if not live or prev is None or not (self.short or self.full):
            return []
        bot = state["players"][bot_slot]
        if not landed(prev["players"][1 - bot_slot], state["players"][1 - bot_slot]):
            return []
        key = (bot["move_id"], frame - bot.get("frame_in_move", 0))
        if key == self.handled:
            return []
        return self.start(state, prev, bot_slot, key)

    def launcher(self, frame):
        move = self.last_move
        if move is None or move.start_frame is None or frame - move.start_frame > LAUNCHER_WINDOW:
            return None
        return move

    def deadline(self, route):
        if not route.get("captured"):
            return LAUNCH_WINDOW
        return max(0, min(e[0] for e in route["inputs"]) - self.seq.latency)

    def start(self, state, prev, bot_slot, key):
        frame = state["frame"]
        bot, target = state["players"][bot_slot], state["players"][1 - bot_slot]
        counter_hit = target["hit_reaction"] in COUNTER_HIT_REACTIONS
        heat = bool(bot.get("heat_active"))
        move = self.launcher(frame)
        short, full = self.candidates(bot["move_id"], counter_hit, heat, move)
        if not short and not full:
            return []
        self.handled = key
        chosen, probs = self.choose(short, full)
        best = (full + short)[0]
        route = self.full.get(chosen) or self.short.get(chosen) or self.full.get(best) or self.short[best]
        notation, start_frame, trigger = move.notation, move.start_frame, move_source(move)
        self.attempt = {
            "route": chosen,
            "route_set": "full" if chosen in self.full else "short" if chosen in self.short else None,
            "options": list(probs),
            "probabilities": probs,
            "launcher": notation,
            "launcher_move_id": bot["move_id"],
            "trigger": trigger,
            "counter_hit": counter_hit,
            "heat": heat,
            "launcher_frame": start_frame,
            "start_frame": frame,
            "distance": round(distance(bot, target)),
            "connect_distance": route.get("connect_distance"),
        }
        if chosen == NONE:
            rec = self.record(state, None, NONE, f"no short route for this launcher at combo_set {self.difficulty.combo_set}")
            self.attempt = None
            return [rec]
        self.seq.discard(lambda m: not m.tag.get("combo"), frame)
        self.pending = {"route": route, "prev": prev, "states": [], "deadline": frame + self.deadline(route),
                        "counter_hit": counter_hit}
        return self.arm(state, True, bot_slot)

    def arm(self, state, live, bot_slot):
        p = self.pending
        frame = state["frame"]
        target = state["players"][1 - bot_slot]
        if p["states"] and frame < p["states"][-1]["frame"]:
            live = False
        p["states"].append(state)
        if live and launched(p["route"], target, p["counter_hit"]):
            self.pending = None
            self.attempt["launch_frame"] = frame
            runner = ComboRunner(p["route"], self.seq, bot_slot, self.difficulty, name=self.attempt["route"], cut=False)
            runner.follow(p["prev"], self.attempt["launcher"], self.attempt["launcher_frame"])
            self.runner = runner
            for buffered in p["states"]:
                runner.on_state(buffered)
                if runner.finished:
                    break
            return self.settle(state)
        lost = not target["hit_reaction"] or target["free_movement"]
        if live and not lost and frame < p["deadline"]:
            return []
        self.pending = None
        if not live:
            why = ROUND_OVER
        elif lost:
            why = "hit reaction lost"
        else:
            why = f"no launch by +{p['deadline'] - self.attempt['start_frame']}"
        rec = self.record(state, None, NO_LAUNCH, f"{why} before the first follow-up input")
        self.attempt = None
        return [rec]

    def advance(self, state, live, bot_slot):
        runner = self.runner
        frame = state["frame"]
        target = state["players"][1 - bot_slot]
        runner.on_state(state)
        if not runner.finished and not live:
            runner.stop(frame, reason=ROUND_OVER)
        elif not runner.finished and runner.index >= 1 and frame > self.attempt["start_frame"] and (
                not target["hit_reaction"] or target["free_movement"]):
            runner.stop(frame, "dropped", f"hit reaction lost before link {runner.index + 1}")
        return self.settle(state)

    def settle(self, state):
        if not self.runner.finished:
            return []
        rec = self.record(state, self.runner)
        self.runner = None
        self.attempt = None
        return [rec]

    def record(self, state, runner, status=None, reason=None):
        a = self.attempt
        detail = {"kind": "combo", **{k: v for k, v in a.items() if k not in ("options", "probabilities")}}
        if runner is None:
            detail.update(links_completed=0, links_planned=0, dropped=False, status=status, reason=reason, damage=0)
        else:
            done, planned = progress(runner)
            detail.update(links_completed=done, links_planned=planned, hits=len(runner.hits),
                          hits_planned=sum(len(link.hits) for link in runner.links), dropped=runner.status != "done" and runner.reason != ROUND_OVER,
                          status=runner.status, reason=runner.reason, damage=runner.damage, listed_damage=runner.listed_damage,
                          end_frame=runner.end_frame, errors=[f"link {link + 1}: {error}" for link, error in runner.errors])
        rec = {
            "t": "tactical",
            "session_id": state["session_id"],
            "round": state["round"],
            "frame": state["frame"],
            "frame_asked": a["start_frame"],
            "options": a["options"],
            "chosen": a["route"] if runner is not None else NONE,
            "probabilities": a["probabilities"],
            "source": "reflex",
            "reflex": detail,
        }
        self.decisions.append(rec)
        return rec
