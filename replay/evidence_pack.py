import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from replay.character_data import CharacterDataError, load_character, load_matchup, normalize_character, normalize_command

PUNISH_WINDOW = 45
FOLLOWUP_WINDOW = 30
WHIFF_WINDOW = 25
STEP_WINDOW = 40
THROW_WINDOW = 90
LOW_LEVELS = {"low", "special_low"}
BREAK_CODES = {"press_1": "1", "press_2": "2", "press_12": "1+2"}
BREAK_ACTIONS = {"break_1": "1", "break_2": "2", "break_12": "1+2"}
STRIKES = {"hit", "counter_hit"}
HUMAN_ATTACKS = {"hit", "counter_hit", "block", "whiff"}
KEEP_SESSIONS = 4


class RecordingTail:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.offset = 0
        self.events = []
        self.summaries = {}
        self.states = {}
        self.human_slots = Counter()
        self.characters = {}
        self.warnings = []

    @classmethod
    def from_records(cls, records):
        tail = cls()
        for record in records:
            tail.add(record.data if hasattr(record, "data") else record)
        return tail

    def add(self, data):
        if not isinstance(data, dict):
            return
        kind = data.get("t")
        if kind == "state":
            try:
                players = {player["slot"]: player for player in data["players"]}
                human = data["human_slot"]
                self.human_slots[human] += 1
                self.characters[human] = players[human].get("character")
                self.characters[1 - human] = players[1 - human].get("character")
                derived = data.get("derived") or {}
                self.states[(data["round"], data["frame"])] = (
                    derived.get("situation"), derived.get("distance_bucket"),
                    players[0].get("health"), players[1].get("health"))
            except (KeyError, TypeError):
                self.warnings.append("Skipped a malformed state record")
        elif kind == "event":
            if isinstance(data.get("round"), int) and isinstance(data.get("frame"), int) and isinstance(data.get("kind"), str):
                self.events.append(data)
        elif kind == "round_summary":
            if isinstance(data.get("round"), int):
                self.summaries[data["round"]] = data

    def refresh(self):
        if self.path is None or not self.path.is_file():
            return self
        with self.path.open("rb") as source:
            source.seek(self.offset)
            while True:
                line = source.readline()
                if not line:
                    break
                complete = line.endswith(b"\n")
                text = line.decode("utf-8", errors="replace")
                if self.offset == 0:
                    text = text.lstrip("﻿")
                stripped = text.strip()
                if stripped:
                    try:
                        data = json.loads(stripped)
                    except ValueError:
                        if not complete:
                            break
                        self.warnings.append("Skipped an unreadable recording line")
                        self.offset += len(line)
                        continue
                    self.add(data)
                self.offset += len(line)
        return self

    @property
    def human_slot(self):
        if len(self.human_slots) != 1:
            return None
        return next(iter(self.human_slots))

    def state_at(self, round_number, frame):
        for back in range(4):
            found = self.states.get((round_number, frame - back))
            if found is not None:
                return found
        return None

    def health(self, round_number, frame, slot):
        state = self.state_at(round_number, frame)
        if state is None:
            return None
        return state[2 + slot]


@dataclass
class MatchupContext:
    human_slot: int
    human: object = None
    bot: object = None
    notes: object = None
    fastest: int = 10
    human_name: str = "unknown"
    bot_name: str = "unknown"
    warnings: list = field(default_factory=list)

    @classmethod
    def load(cls, human_slot, human_character, bot_character):
        ctx = cls(human_slot=human_slot)
        ctx.human_name = normalize_character(human_character) or "unknown"
        ctx.bot_name = normalize_character(bot_character) or "unknown"
        try:
            ctx.human = load_character(human_character)
        except (CharacterDataError, OSError, ValueError, KeyError):
            ctx.warnings.append("Human character data is unavailable; punishers are omitted")
        try:
            ctx.bot = load_character(bot_character)
        except (CharacterDataError, OSError, ValueError, KeyError):
            ctx.warnings.append("Opponent character data is unavailable; opponent moves are unnamed")
        if ctx.human is not None and ctx.bot is not None:
            try:
                ctx.notes = load_matchup(human_character, bot_character)
            except (CharacterDataError, OSError, ValueError, KeyError):
                ctx.notes = None
        if ctx.human is not None:
            startups = [entry.get("startup") for tier in ctx.human.punishers.get("tiers", {}).values()
                        for entry in tier.get("standing", []) if type(entry.get("startup")) is int]
            if startups:
                ctx.fastest = min(startups)
        return ctx


def _level(value):
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, str):
        return None
    return value.split("/")[0].strip() or None


def describe(character, move_id):
    info = {"move_id": move_id, "resolved": False, "name": None, "command": None, "hit_level": None,
            "on_block": None, "startup": None, "tracking": "", "listed_damage": None}
    if character is None or move_id is None:
        return info
    resolution = character.resolve_move_id(move_id)
    if not resolution.found:
        return info
    move = resolution.move
    info.update(resolved=True, name=move.get("name") or None, command=move["command"], hit_level=_level(move.get("hit_level")),
                on_block=move.get("on_block") if type(move.get("on_block")) is int else None,
                startup=move.get("startup") if type(move.get("startup")) is int else None,
                tracking=move.get("tracking") or "")
    listed = str(move.get("damage") or "").split(",")[-1]
    info["listed_damage"] = int(listed) if listed.isdigit() else None
    return info


def plus_on_block(ctx, move):
    if ctx.notes is None or not move.get("command"):
        return False
    rows = ctx.notes.tables.get("Moves that leave them plus on block (do not press buttons)", [])
    return any(normalize_command(row.get("Move", "")) == normalize_command(move["command"]) for row in rows)


def punisher_for(ctx, move):
    on_block = move.get("on_block")
    if ctx.human is None or type(on_block) is not int or on_block > -ctx.fastest:
        return None
    crouching = move.get("hit_level") in LOW_LEVELS
    tier = ctx.human.punish_tier(on_block, crouching=crouching)
    command = None
    if not crouching and ctx.notes is not None:
        row = ctx.notes.punish_row(move.get("command") or "")
        if row and row.get("Punish with"):
            command = row["Punish with"].strip("`")
    if command is None and tier:
        command = tier[0]["command"]
    if not command:
        return None
    entry = next((item for item in tier if item.get("command") == command), None)
    listed = ctx.human.by_command.get(command)
    return {"command": command, "name": listed.get("name") if listed else None,
            "damage": entry.get("damage") if entry and type(entry.get("damage")) is int else None,
            "startup": entry.get("startup") if entry else (listed.get("startup") if listed else None)}


def _bucket(tail, round_number, frame):
    state = tail.state_at(round_number, frame)
    return state[1] if state else None


def _situation(tail, round_number, frame):
    state = tail.state_at(round_number, frame)
    return (state[0] if state else None) or "unknown"


def _window(indexed, round_number, start, end, predicate):
    return [event for event in indexed.get(round_number, []) if start < event["frame"] <= end and predicate(event)]


def build_pack(tail, ctx, round_number=None, decisions=None, summary=None):
    human, bot = ctx.human_slot, 1 - ctx.human_slot
    events = [event for event in tail.events if round_number is None or event["round"] == round_number]
    indexed = defaultdict(list)
    for event in events:
        indexed[event["round"]].append(event)
    for rows in indexed.values():
        rows.sort(key=lambda event: event["frame"])
    if decisions is None:
        decisions = [event for event in events if event["kind"] == "decision_point" and event.get("actor") == human]
    else:
        decisions = [point for point in decisions if round_number is None or point["round"] == round_number]
    rounds = sorted(indexed)

    hits = {}
    damage_by_situation = Counter()
    for event in events:
        if event["kind"] in STRIKES and event.get("target") == human and event.get("actor") == bot:
            damage = event.get("damage") if type(event.get("damage")) is int else 0
            damage_by_situation[_situation(tail, event["round"], event["frame"])] += damage
            entry = hits.setdefault(event.get("move_id"), {**describe(ctx.bot, event.get("move_id")), "count": 0, "damage": 0,
                                                             "counter_hits": 0, "buckets": Counter(), "citations": [],
                                                             "level": event.get("hit_level")})
            entry["count"] += 1
            entry["damage"] += damage
            entry["counter_hits"] += event["kind"] == "counter_hit"
            bucket = _bucket(tail, event["round"], event["frame"])
            if bucket:
                entry["buckets"][bucket] += 1
            entry["citations"].append({"round": event["round"], "frame": event["frame"]})
    hits_taken = []
    for entry in hits.values():
        entry["distance"] = entry["buckets"].most_common(1)[0][0] if entry["buckets"] else None
        entry["buckets"] = dict(entry["buckets"])
        if not entry["hit_level"]:
            entry["hit_level"] = entry["level"]
        entry["punisher"] = punisher_for(ctx, entry)
        entry["plus_on_block"] = plus_on_block(ctx, entry)
        hits_taken.append(entry)
    hits_taken.sort(key=lambda entry: (entry["damage"], entry["count"]), reverse=True)

    throws = []
    throw_points = {(point["round"], (point.get("detail") or {}).get("start_frame")): point
                    for point in decisions if point.get("situation") == "throw_break"}
    for event in events:
        if event["kind"] != "throw" or event.get("target") != human:
            continue
        code = (event.get("detail") or {}).get("break")
        point = throw_points.get((event["round"], event["frame"]))
        if point is not None:
            pressed = BREAK_ACTIONS.get(point.get("action"))
            broken = bool((point.get("detail") or {}).get("correct"))
        else:
            escaped = _window(indexed, event["round"], event["frame"] - 1, event["frame"] + THROW_WINDOW,
                              lambda item: item["kind"] == "throw_break" and item.get("actor") == human)
            pressed = BREAK_CODES.get((escaped[0].get("detail") or {}).get("input")) if escaped else None
            broken = bool(escaped)
        move = describe(ctx.bot, event.get("move_id"))
        break_input = BREAK_CODES.get(code)
        if move["command"] and ctx.bot is not None:
            listed = ctx.bot.throw_break(move["command"])
            if listed in {"1", "2", "1+2"}:
                break_input = break_input or listed
        before = tail.health(event["round"], event["frame"], human)
        after = tail.health(event["round"], event["frame"] + THROW_WINDOW, human)
        damage = 0
        if not broken:
            if move["listed_damage"] is not None:
                damage = move["listed_damage"]
            elif before is not None and after is not None:
                damage = max(0, before - after)
        damage_by_situation["throw"] += damage
        throws.append({**move, "frame": event["frame"], "round": event["round"], "break_input": break_input,
                       "pressed": pressed, "broken": broken, "damage": damage,
                       "citations": [{"round": event["round"], "frame": event["frame"]}]})

    whiffs = []
    for event in events:
        if event["kind"] != "whiff" or event.get("actor") != human:
            continue
        start = (event.get("detail") or {}).get("start_frame", event["frame"])
        punish = _window(indexed, event["round"], start, event["frame"] + WHIFF_WINDOW,
                         lambda item: item["kind"] in STRIKES and item.get("actor") == bot and item.get("target") == human)
        punished = None
        if punish:
            punished = {**describe(ctx.bot, punish[0].get("move_id")), "frame": punish[0]["frame"],
                        "damage": punish[0].get("damage") if type(punish[0].get("damage")) is int else 0}
        whiffs.append({**describe(ctx.human, event.get("move_id")), "frame": event["frame"], "round": event["round"],
                       "distance": _bucket(tail, event["round"], start), "punished_by": punished,
                       "citations": [{"round": event["round"], "frame": event["frame"]}]})

    presses = []
    for point in decisions:
        situation = point.get("situation") or ""
        if not situation.startswith("after_block:") or point.get("action") != "press":
            continue
        detail = point.get("detail") or {}
        adv = detail.get("adv")
        start = detail.get("start_frame", point["frame"])
        followup = _window(indexed, point["round"], start, point["frame"] + FOLLOWUP_WINDOW,
                           lambda item: item["kind"] in STRIKES and item.get("actor") == bot and item.get("target") == human)
        blocked = describe(ctx.bot, point.get("move_id"))
        if blocked["on_block"] is None and type(adv) is int:
            blocked["on_block"] = -adv
        presses.append({"blocked": blocked, "human_advantage": adv if type(adv) is int else None,
                        "response": describe(ctx.human, detail.get("response_move_id")),
                        "followup": {**describe(ctx.bot, followup[0].get("move_id")),
                                     "damage": followup[0].get("damage") if type(followup[0].get("damage")) is int else 0,
                                     "frame": followup[0]["frame"]} if followup else None,
                        "frame": point["frame"], "round": point["round"],
                        "citations": [{"round": point["round"], "frame": point["frame"]}]})

    missed = []
    punished = []
    for event in events:
        if event["kind"] != "block" or event.get("actor") != bot or event.get("target") != human:
            continue
        advantage = event.get("frame_advantage")
        if type(advantage) is not int or -advantage < ctx.fastest:
            continue
        landed = _window(indexed, event["round"], event["frame"], event["frame"] + PUNISH_WINDOW,
                         lambda item: item["kind"] in STRIKES and item.get("actor") == human and item.get("target") == bot)
        if landed:
            punished.append({"blocked": describe(ctx.bot, event.get("move_id")), "human_advantage": -advantage,
                             "punish": {**describe(ctx.human, landed[0].get("move_id")),
                                        "damage": landed[0].get("damage") if type(landed[0].get("damage")) is int else 0},
                             "frame": event["frame"], "round": event["round"],
                             "citations": [{"round": event["round"], "frame": event["frame"]}]})
            continue
        attempted = _window(indexed, event["round"], event["frame"], event["frame"] + PUNISH_WINDOW,
                            lambda item: item["kind"] in HUMAN_ATTACKS and item.get("actor") == human)
        blocked = describe(ctx.bot, event.get("move_id"))
        blocked["on_block"] = advantage
        if event.get("hit_level") and not blocked["hit_level"]:
            blocked["hit_level"] = event["hit_level"]
        missed.append({"blocked": blocked, "human_advantage": -advantage, "attempted": bool(attempted),
                       "punisher": punisher_for(ctx, blocked), "frame": event["frame"], "round": event["round"],
                       "citations": [{"round": event["round"], "frame": event["frame"]}]})

    steps = []
    for point in decisions:
        if point.get("situation") != "sidestep_dir" or point.get("action") != "none":
            continue
        detail = point.get("detail") or {}
        start = detail.get("start_frame", point["frame"])
        struck = _window(indexed, point["round"], start - 1, point["frame"] + STEP_WINDOW,
                         lambda item: item["kind"] in STRIKES and item.get("actor") == bot and item.get("target") == human
                         and item.get("move_id") == point.get("move_id"))
        steps.append({**describe(ctx.bot, point.get("move_id")), "frame": point["frame"], "round": point["round"],
                      "damage": struck[0].get("damage", 0) if struck and type(struck[0].get("damage")) is int else 0,
                      "hit": bool(struck), "citations": [{"round": point["round"], "frame": point["frame"]}]})

    whiff_punishes = []
    for event in events:
        if event["kind"] != "whiff" or event.get("actor") != bot:
            continue
        start = (event.get("detail") or {}).get("start_frame", event["frame"])
        landed = _window(indexed, event["round"], start, event["frame"] + WHIFF_WINDOW,
                         lambda item: item["kind"] in STRIKES and item.get("actor") == human and item.get("target") == bot)
        if landed:
            whiff_punishes.append({**describe(ctx.bot, event.get("move_id")), "frame": event["frame"], "round": event["round"],
                                   "punish": {**describe(ctx.human, landed[0].get("move_id")),
                                              "damage": landed[0].get("damage") if type(landed[0].get("damage")) is int else 0},
                                   "citations": [{"round": event["round"], "frame": event["frame"]}]})

    lows = {}
    for point in decisions:
        if point.get("situation") != "low_defense":
            continue
        entry = lows.setdefault(point.get("move_id"), {"hit": 0, "blocked": 0, "other": 0, "citations": []})
        action = point.get("action")
        key = "hit" if action == "hit" else "blocked" if action in {"blocked", "low_parry"} else "other"
        entry[key] += 1
        entry["citations"].append({"round": point["round"], "frame": point["frame"]})

    return {
        "session_id": summary.get("session_id") if summary else None,
        "round": round_number, "rounds": rounds, "human_slot": human,
        "human_character": ctx.human_name, "bot_character": ctx.bot_name,
        "damage_taken_by_situation": dict(damage_by_situation),
        "hits_taken": hits_taken, "throws": throws, "whiffs": whiffs, "presses": presses,
        "missed_punishes": missed, "punishes_landed": punished, "whiff_punishes_landed": whiff_punishes,
        "sidesteps": steps, "low_decisions": lows, "decisions": decisions,
        "rates": habit_rates(decisions),
        "habits": list((summary or {}).get("top_habits", [])),
        "damage_taken": (summary or {}).get("human_damage_taken"),
        "newly_fixed": list((summary or {}).get("newly_fixed", [])),
        "regressed": list((summary or {}).get("regressed", [])),
        "warnings": list(ctx.warnings) + list(tail.warnings),
    }


def habit_rates(decisions):
    counts = {"low_defense": Counter(), "throw_break": Counter(), "after_block": Counter(), "sidestep_dir": Counter()}
    for point in decisions:
        situation = point.get("situation") or ""
        action = point.get("action")
        detail = point.get("detail") or {}
        if situation == "low_defense":
            counts["low_defense"]["bad" if action == "hit" else "good"] += 1
        elif situation == "throw_break":
            counts["throw_break"]["good" if detail.get("correct") else "bad"] += 1
        elif situation == "sidestep_dir":
            counts["sidestep_dir"]["bad" if action == "none" else "good"] += 1
        elif situation.startswith("after_block:") and type(detail.get("adv")) is int and detail["adv"] <= 0:
            counts["after_block"]["bad" if action == "press" else "good"] += 1
    rates = {}
    for key, counter in counts.items():
        total = counter["bad"] + counter["good"]
        rates[key] = {"n": total, "bad": counter["bad"], "p": counter["bad"] / total if total else 0.0}
    return rates


class EvidenceStore:
    def __init__(self, data_dir, keep=KEEP_SESSIONS):
        self.data_dir = Path(data_dir).resolve()
        self.keep = keep
        self.tails = {}

    def tail(self, session_id):
        from replay.reports import checked_id, within

        try:
            checked_id(session_id)
            path = within(self.data_dir, self.data_dir / "recordings" / f"{session_id}.jsonl")
        except ValueError:
            return None
        if not path.is_file():
            return None
        tail = self.tails.get(session_id)
        if tail is None:
            tail = RecordingTail(path)
            self.tails[session_id] = tail
            while len(self.tails) > self.keep:
                del self.tails[next(iter(self.tails))]
        return tail.refresh()

    def round_pack(self, summary):
        session_id = summary.get("session_id")
        if not isinstance(session_id, str):
            return None
        tail = self.tail(session_id)
        if tail is None or not tail.events:
            return None
        human_slot = summary.get("human_slot")
        if tail.human_slot is not None and tail.human_slot != human_slot:
            return None
        human = summary.get("human_character") or tail.characters.get(human_slot)
        bot = summary.get("bot_character") or tail.characters.get(1 - human_slot)
        ctx = MatchupContext.load(human_slot, human, bot)
        return build_pack(tail, ctx, round_number=summary.get("round"), summary=summary)


def set_pack(records, decisions=None):
    tail = RecordingTail.from_records(records)
    human_slot = tail.human_slot
    if human_slot is None:
        return None
    ctx = MatchupContext.load(human_slot, tail.characters.get(human_slot), tail.characters.get(1 - human_slot))
    latest = tail.summaries[max(tail.summaries)] if tail.summaries else None
    pack = build_pack(tail, ctx, round_number=None, decisions=decisions, summary=latest)
    pack["per_round"] = {number: build_pack(tail, ctx, round_number=number, decisions=decisions, summary=tail.summaries.get(number))
                         for number in pack["rounds"]}
    return pack
