import json
import math
import re
import statistics
from dataclasses import dataclass, replace
from pathlib import Path

from game.notation import NEUTRAL, compile_notation
from game.sequencer import Move, apply_execution_error, first_press

ROUTES_PATH = Path(__file__).resolve().parent / "combos_kazuya.json"
CAPTURED_DIR = Path(__file__).resolve().parent / "combos_captured"
SHORT_MAX_LEVEL = 2
SHORT_HITS = 2
FINISHED = ("done", "dropped", "interrupted", "aborted")
KI_CHARGE = ("1", "2", "3", "4")
COUNTER_HIT_REACTIONS = (10, 11)
MAX_APPROACH_FRAMES = 40
FIRST_DIRECTION = re.compile(r"^([udfb]{1,2})(?=\+)")


def load_routes(path=ROUTES_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def hit_limit(difficulty):
    if difficulty is not None and difficulty.level <= SHORT_MAX_LEVEL:
        return SHORT_HITS
    return None


@dataclass(frozen=True)
class Link:
    notation: str
    hits: tuple
    lead: str = ""
    body: str = ""
    hold: int = 0
    delay: int = 0


def link_notation(lead, command):
    return f"{lead},{command}" if lead else command


def held_body(command, hold):
    if hold <= 0:
        return command
    return FIRST_DIRECTION.sub(lambda m: m.group(1).upper(), command, count=1)


def plan(route, limit=None):
    links = []
    left = limit
    for seg in route["segments"]:
        hits = seg["hits"] if left is None else seg["hits"][:left]
        if not hits:
            break
        lead = seg.get("lead") or ""
        hold = int(seg.get("hold") or 0)
        body = held_body(hits[-1]["command"], hold)
        links.append(Link(link_notation(lead, body), tuple(hits), lead, body, hold, int(seg.get("delay") or 0)))
        if left is not None:
            left -= len(hits)
    return links


def listed_damage(links):
    return sum(h["damage"] for link in links for h in link.hits)


def last_press(frames):
    presses = [i for i, mask in enumerate(frames) if mask[1] and (i == 0 or frames[i - 1] != mask)]
    return presses[-1] if presses else 0


def load_captured(name, directory=CAPTURED_DIR):
    return json.loads((Path(directory) / f"{name}.json").read_text(encoding="utf-8"))


def captured_cut(route, limit):
    hits = route["hits"]
    if limit is None or limit >= len(hits):
        return None
    return hits[limit - 1][0]


def captured_links(route, limit=None):
    hits = route["hits"]
    count = len(hits) if limit is None else min(limit, len(hits))
    first = {"command": route["launcher"], "move_id": route.get("launcher_move_id"), "damage": hits[0][1] if hits else 0}
    links = [Link(route["launcher"], (first,), body=route["launcher"])]
    rest = tuple({"command": None, "move_id": h[2], "damage": h[1]} for h in hits[1:count])
    if rest:
        links.append(Link(f"captured:{route['name']}", rest))
    return links


def captured_frames(inputs, cut=None):
    events = sorted((e for e in inputs if cut is None or e[0] <= cut), key=lambda e: e[0])
    if not events:
        return [], 0
    start = events[0][0]
    end = max(max(o + 1, o + hold) for o, _, _, hold in events)
    frames = []
    direction = "n"
    k = 0
    for t in range(start, end):
        while k < len(events) and events[k][0] <= t:
            direction = events[k][1]
            k += 1
        buttons = sorted({b for o, _, bs, hold in events if bs and o <= t < o + max(1, hold) for b in bs})
        frames.append((direction, tuple(buttons)))
    frames.append(NEUTRAL)
    return frames, start


def distance(a, b):
    return math.hypot(b.get("x", 0) - a.get("x", 0), b.get("z", 0) - a.get("z", 0))


def ki_charging(player):
    return set(KI_CHARGE) <= set(player.get("buttons_held", [])) | set(player.get("buttons_pressed", []))


def connect_signal(prev_target, target):
    return target["health"] < prev_target["health"] or bool(target["hit_reaction"] and not prev_target["hit_reaction"])


def trace_row(frame, index, bot, target):
    return {"frame": frame, "link": index, "bot_move": bot["move_id"], "bot_free": bot["free_movement"],
            "bot_side": bot.get("side"), "bot_y": bot.get("y"), "dir": bot.get("dir_held"),
            "bot_until": bot["frames_until_actionable"], "target_move": target["move_id"],
            "basic_state": target.get("basic_state"), "status": target.get("status"), "y": target.get("y"),
            "distance": round(math.hypot(target.get("x", 0) - bot.get("x", 0), target.get("z", 0) - bot.get("z", 0))),
            "health": target["health"], "reaction": target["hit_reaction"]}


class ComboRunner:
    def __init__(self, route, sequencer, bot_slot, difficulty=None, name=None, trace=False):
        self.name = name
        self.seq = sequencer
        self.bot = bot_slot
        self.difficulty = difficulty if difficulty is not None else sequencer.difficulty
        self.captured = route if route.get("captured") else None
        if self.captured:
            limit = hit_limit(self.difficulty)
            self.cut = captured_cut(route, limit)
            self.links = captured_links(route, limit)
            self.attacks = [a for a in route["attacks"] if self.cut is None or a[0] <= self.cut]
            self.planned_hits = sum(len(link.hits) for link in self.links)
            self.connect_frame = None
            self.replay = None
            self.attack_index = 0
            self.pending_attack = False
            self.charged = False
            self.approach_start = None
            self.opener_distance = None
            self.reach = None
        else:
            self.links = plan(route, hit_limit(self.difficulty))
        self.listed_damage = listed_damage(self.links)
        self.index = 0
        self.move = None
        self.final_entry = None
        self.ready_frame = None
        self.status = "ready"
        self.reason = None
        self.end_frame = None
        self.hits = []
        self.submitted = []
        self.connects = {}
        self.trace = [] if trace else None
        self.prev = None

    @property
    def finished(self):
        return self.status in FINISHED

    @property
    def damage(self):
        return sum(h["damage"] for h in self.hits)

    @property
    def errors(self):
        return [(s["link"], s["error"]) for s in self.submitted if s["error"]]

    @property
    def first_reaction(self):
        return self.hits[0]["reaction"] if self.hits else None

    def stop(self, frame=None, status="aborted", reason=None):
        if not self.finished:
            self.seq.cancel(frame)
            self.status = status
            self.reason = reason
            self.end_frame = frame

    def on_state(self, state):
        if self.finished:
            return None
        frame = state["frame"]
        bot = state["players"][self.bot]
        target = state["players"][1 - self.bot]
        if self.trace is not None:
            self.trace.append(trace_row(frame, self.index, bot, target))
        prev = self.prev
        self.prev = state
        if prev is not None:
            if frame < prev["frame"]:
                self.stop(frame, reason="round frame counter went back")
                return None
            if bot["health"] < prev["players"][self.bot]["health"]:
                self.stop(frame, "interrupted", "bot was hit")
                return None
        if self.captured:
            return self._captured_step(frame, bot, target, prev)
        if prev is not None:
            self._track(frame, bot, target, prev)
        if self.move is not None and self._resolve(frame, bot):
            return None
        if self.move is None and self._ready(bot):
            if self.ready_frame is None:
                self.ready_frame = frame
            if frame - self.ready_frame >= self.links[self.index].delay:
                return self._submit(frame)
        return None

    def _track(self, frame, bot, target, prev):
        if not self.submitted:
            return
        started = self.move is not None and self.move.start_frame is not None
        if started and self.final_entry is None:
            pressed = self.move.start_frame + last_press(self.move.frames) + self.seq.latency
            if frame >= pressed and bot["move_id"] != prev["players"][self.bot]["move_id"]:
                self.final_entry = frame
        drop = prev["players"][1 - self.bot]["health"] - target["health"]
        if drop > 0:
            final = started and self.final_entry is not None and frame >= self.final_entry
            link = self.index if self.move is not None else self.index - 1
            self.hits.append({"frame": frame, "damage": drop, "move_id": bot["move_id"], "link": link,
                              "reaction": target["hit_reaction"], "final": final})

    def _connected(self):
        hits = [h for h in self.hits if h["link"] == self.index]
        need = sum(1 for h in self.links[self.index].hits if not h.get("optional"))
        return len(hits) >= need and any(h["final"] for h in hits)

    def _resolve(self, frame, bot):
        if self.move.cancelled:
            self.status = "aborted"
            self.reason = "sequencer cancelled the input"
            self.end_frame = frame
            return True
        if self._connected():
            self.connects[self.index] = frame
            self.index += 1
            self.move = None
            self.final_entry = None
            self.ready_frame = None
            if self.index == len(self.links):
                self.status = "done"
                self.end_frame = frame
                return True
            return False
        if self.move.done_frame is not None and bot["free_movement"]:
            self.status = "dropped"
            self.end_frame = frame
            return True
        return False

    def _ready(self, bot):
        link = self.links[self.index]
        if bot["free_movement"]:
            return True
        if link.lead:
            return False
        lead = first_press(compile_notation(link.body, self.body_timing(link)))
        return bot["frames_until_actionable"] <= self.seq.latency + lead

    def body_timing(self, link):
        if link.hold <= 0:
            return self.seq.timing
        return replace(self.seq.timing, hold_frames=link.hold + self.seq.timing.press_frames)

    def _finish(self, frame, status, reason=None):
        self.status = status
        self.reason = reason
        self.end_frame = frame
        return None

    def _captured_step(self, frame, bot, target, prev):
        if self.move is None:
            ki = self.captured.get("trigger") == "ki_charge"
            if ki:
                self.charged = self.charged or ki_charging(target)
                if not self.charged:
                    return None
            elif frame < self.captured.get("start_round_frame", 0):
                return None
            if not self._ready(bot):
                return None
            if self.captured.get("launcher_inputs_replay"):
                if self._approach(frame, bot, target):
                    return None
                self.opener_distance = distance(bot, target)
            return self._submit_opener(frame) if self.captured.get("launcher_inputs_replay") else self._submit(frame)
        if prev is None:
            return None
        prev_bot, prev_target = prev["players"][self.bot], prev["players"][1 - self.bot]
        drop = prev_target["health"] - target["health"]
        if drop > 0 and self.move.start_frame is not None:
            self.hits.append({"frame": frame, "damage": drop, "move_id": bot["move_id"], "link": 0 if not self.hits else 1,
                              "reaction": target["hit_reaction"], "final": True})
        if self.connect_frame is None:
            if self.move.start_frame is not None and connect_signal(prev_target, target):
                self.connect_frame = frame
                self.connects[0] = frame
                if self.opener_distance is not None and self._opener_landed(bot):
                    self.reach = round(self.opener_distance - distance(bot, target))
                    reaches = self.captured.setdefault("reaches", [])
                    reaches.append(self.reach)
                    self.captured["learned_reach"] = round(statistics.median(reaches))
                self.index = 1
                self._schedule(frame)
            elif self.move.done_frame is not None and bot["free_movement"]:
                return self._finish(frame, "dropped", "launcher missed")
            else:
                return None
        if len(self.hits) >= self.planned_hits:
            self.index = len(self.links)
            return self._finish(frame, "done")
        if frame > self.connect_frame and bot["move_id"] != prev_bot["move_id"]:
            self.pending_attack = True
        if self.pending_attack and frame > self.connect_frame and bot["hit_level"] != "none":
            self.pending_attack = False
            offset = frame - self.connect_frame
            if self.attack_index >= len(self.attacks) or bot["move_id"] != int(self.attacks[self.attack_index][1], 16):
                want = self.attacks[self.attack_index] if self.attack_index < len(self.attacks) else None
                expected = f"expected {want[1]} at +{want[0]}" if want else "expected no more attacks"
                self.stop(frame, reason=f"diverged: move 0x{bot['move_id']:04X} at +{offset}, {expected}")
                return None
            self.attack_index += 1
        replay = self.replay
        if replay is not None and replay.cancelled:
            return self._finish(frame, "aborted", "sequencer cancelled the input")
        if (replay is None or replay.done_frame is not None) and bot["free_movement"]:
            return self._finish(frame, "dropped", f"inputs finished with {len(self.hits)}/{self.planned_hits} hits")
        return None

    def _schedule(self, connect):
        frames, start = captured_frames(self.captured["inputs"], self.cut)
        if not frames:
            return
        error = None
        if self.difficulty is not None:
            frames, error = apply_execution_error(frames, self.difficulty.execution_error, self.seq.rng)
        move = Move(f"captured:{self.captured['name']}", frames, earliest=connect + start - self.seq.latency, force=True,
                    tag={"combo": self.name, "link": 1}, queued_frame=connect)
        self.seq.queue.append(move)
        self.replay = move
        self.submitted.append({"frame": connect, "link": 1, "notation": move.notation, "error": error})

    def _opener_landed(self, bot):
        hits = self.captured.get("hits") or []
        return not hits or bot["move_id"] == int(hits[0][2], 16)

    def fire_distance(self):
        reach = self.captured.get("learned_reach", self.captured.get("opener_reach"))
        want = self.captured.get("connect_distance")
        return None if reach is None or want is None else want + reach

    def _approach(self, frame, bot, target):
        fire = self.fire_distance()
        if fire is None:
            return False
        if self.approach_start is None:
            self.approach_start = frame
        if distance(bot, target) > fire and frame - self.approach_start < MAX_APPROACH_FRAMES:
            self.seq.hold("f")
            return True
        self.seq.hold("n")
        return False

    def _submit_opener(self, frame):
        frames, _ = captured_frames(self.captured["launcher_inputs"])
        error = None
        if self.difficulty is not None:
            frames, error = apply_execution_error(frames, self.difficulty.execution_error, self.seq.rng)
        move = Move(f"captured:{self.captured['name']}:opener", frames, force=True, lead=first_press(frames),
                    tag={"combo": self.name, "link": 0}, queued_frame=frame)
        self.seq.queue.append(move)
        self.move = move
        self.status = "running"
        self.submitted.append({"frame": frame, "link": 0, "notation": self.captured["launcher"], "error": error})
        return self.captured["launcher"]

    def _submit(self, frame):
        link = self.links[self.index]
        if link.lead:
            self.seq.submit(link.lead, frame=frame, force=True, error=False, combo=self.name, link=self.index, part="lead")
        self.move = self.seq.submit(link.body, frame=frame, force=True, timing=self.body_timing(link),
                                    combo=self.name, link=self.index)
        self.status = "running"
        self.submitted.append({"frame": frame, "link": self.index, "notation": link.notation, "error": self.move.error})
        return link.notation
