import json
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path

from game.notation import compile_notation
from game.sequencer import first_press

ROUTES_PATH = Path(__file__).resolve().parent / "combos_kazuya.json"
SHORT_MAX_LEVEL = 2
SHORT_HITS = 2
FINISHED = ("done", "dropped", "interrupted", "aborted")
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

    def _submit(self, frame):
        link = self.links[self.index]
        if link.lead:
            self.seq.submit(link.lead, frame=frame, force=True, error=False, combo=self.name, link=self.index, part="lead")
        self.move = self.seq.submit(link.body, frame=frame, force=True, timing=self.body_timing(link),
                                    combo=self.name, link=self.index)
        self.status = "running"
        self.submitted.append({"frame": frame, "link": self.index, "notation": link.notation, "error": self.move.error})
        return link.notation
