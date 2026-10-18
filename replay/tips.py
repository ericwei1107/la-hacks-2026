import re
from dataclasses import dataclass, field

from replay.character_data import CharacterDataError, load_character, normalize_command

MIN_N = 3
MAX_WORDS = 30
TOPIC_LABELS = {
    "low_defense": "low blocking", "throw_break": "throw breaking", "after_block": "pressing after block",
    "sidestep_dir": "sidestep timing", "neutral": "neutral defense", "whiff_punish": "whiffing",
    "missed_punish": "punishing",
}
FIXED_LABELS = {"low_defense": "low blocking", "throw_break": "throw breaking", "after_block": "guarding after block",
                "sidestep_dir": "sidestepping"}
NUMBER = re.compile(r"(?<![\w+,~/])[-+]?\d+(?:\.\d+)?")
COMMAND = re.compile(r"(?<![\w])(?:(?:[ubdf]{1,2}|ws|fc|wr|ss|cd)\+?)?[1-4](?:[+,~][1-4])+(?![\w])"
                     r"|(?<![\w])(?:[ubdf]{1,2}|ws|fc|wr|ss|cd)\+?[1-4](?![\w])"
                     r"|(?<![\w])f,n,d,df\+[1-4](?![\w])|(?<![\w])0x[0-9a-f]+(?![\w])", re.IGNORECASE)


@dataclass
class Candidate:
    topic: str
    text: str
    severity: str
    damage: int = 0
    strength: float = 0.0
    moves: list = field(default_factory=list)
    numbers: list = field(default_factory=list)
    detail: dict = field(default_factory=dict)
    citations: list = field(default_factory=list)

    @property
    def score(self):
        return self.damage * self.strength

    def facts(self):
        return {"topic": self.topic, "moves": list(self.moves), "numbers": list(self.numbers), **self.detail}


def _words(text):
    return len(text.split())


def times(count):
    return "once" if count == 1 else "twice" if count == 2 else f"{count} times"


def _label(move, fallback):
    if move.get("name") and move.get("command"):
        return f"{move['name']} ({move['command']})"
    if move.get("command"):
        return move["command"]
    return fallback


def _names(*moves):
    out = []
    for move in moves:
        if not move:
            continue
        for key in ("name", "command"):
            value = move.get(key)
            if value and value not in out:
                out.append(value)
    return out


def _bot(pack):
    return str(pack.get("bot_character") or "the opponent").replace("_", " ").title()


def _rate(pack, key, fallback_bad, fallback_total):
    habits = {habit["situation"]: habit for habit in pack.get("habits", [])}
    habit = habits.get(key)
    rate = pack.get("rates", {}).get(key, {})
    n = max(rate.get("n", 0), habit["n"] if habit else 0, fallback_total)
    if habit and habit.get("n", 0) >= rate.get("n", 0):
        p = habit["p"]
    elif rate.get("n"):
        p = rate["p"]
    else:
        p = fallback_bad / fallback_total if fallback_total else 0.0
    return n, p


def low_defense(pack):
    lows = [entry for entry in pack["hits_taken"] if (entry.get("hit_level") in {"low", "special_low"}) and entry["count"]]
    if not lows:
        return None
    hit_count = sum(entry["count"] for entry in lows)
    damage = sum(entry["damage"] for entry in lows)
    n, p = _rate(pack, "low_defense", hit_count, hit_count)
    if n < MIN_N or p < 0.5:
        return None
    top = lows[0]
    numbers = [top["count"], top["damage"], hit_count, damage]
    if top["resolved"]:
        label = _label(top, "a low")
        answer = "Crouch-block it, then stand guard."
        moves = _names(top)
        if top.get("punisher"):
            answer = f"Crouch-block it, then punish with {top['punisher']['command']}."
            moves = _names(top, top["punisher"])
        text = f"{label} is a low; it hit you {times(top['count'])} for {top['damage']}. {answer}"
    else:
        text = f"Lows hit you {times(hit_count)} for {damage} this round. Crouch-block the low, then return to standing guard."
        moves = []
    return Candidate("low_defense", text, "warn", damage, max(p, 0.1), moves, numbers,
                     {"opponent_move": {key: top.get(key) for key in ("name", "command", "hit_level", "on_block", "distance")},
                      "hits": top["count"], "damage": top["damage"], "all_lows_hits": hit_count, "all_lows_damage": damage,
                      "punisher": top.get("punisher"), "habit_p": round(p, 2), "habit_n": n},
                     top["citations"][:2])


def throw_break(pack):
    landed = [throw for throw in pack["throws"] if not throw["broken"]]
    if not landed:
        return None
    n, p = _rate(pack, "throw_break", len(landed), len(pack["throws"]))
    if n < MIN_N or p < 0.5:
        return None
    groups = {}
    for throw in landed:
        groups.setdefault((throw.get("command"), throw.get("break_input")), []).append(throw)
    (_, break_input), group = max(groups.items(), key=lambda item: (sum(t["damage"] for t in item[1]), len(item[1])))
    damage = sum(throw["damage"] for throw in landed)
    top = group[0]
    count = len(group)
    numbers = [count, damage, len(landed)]
    moves = []
    if top["resolved"]:
        label = _label(top, "a throw")
        moves = _names(top)
    else:
        label = "A throw"
    if break_input:
        moves.append(break_input)
        text = f"{label} landed {times(count)}. Break it with {break_input}: press {break_input} as the grab starts."
    else:
        text = f"{label} landed {times(count)} for {damage}. Watch the grab animation and press the matching break."
    return Candidate("throw_break", text, "warn", damage, max(p, 0.1), moves, numbers,
                     {"throw": {key: top.get(key) for key in ("name", "command")}, "break_input": break_input,
                      "landed": count, "damage": damage, "total_unbroken": len(landed),
                      "pressed": [throw.get("pressed") for throw in group], "habit_p": round(p, 2), "habit_n": n},
                     [c for throw in group for c in throw["citations"]][:2])


def after_block(pack):
    bad = [press for press in pack["presses"] if type(press["human_advantage"]) is int and press["human_advantage"] <= 0]
    if not bad:
        return None
    n, p = _rate(pack, "after_block", len(bad), len(bad))
    habits = {habit["situation"]: habit for habit in pack.get("habits", [])}
    plus = habits.get("after_block:bot_plus")
    if plus and plus.get("action") == "press" and plus.get("n", 0) >= n:
        n, p = plus["n"], plus["p"]
    if n < MIN_N or p < 0.5:
        return None
    damage = sum(press["followup"]["damage"] for press in bad if press["followup"])
    groups = {}
    for press in bad:
        groups.setdefault(press["blocked"].get("move_id"), []).append(press)
    group = max(groups.values(), key=lambda items: (sum(i["followup"]["damage"] if i["followup"] else 0 for i in items), len(items)))
    top = group[0]
    blocked = top["blocked"]
    on_block = blocked.get("on_block")
    count = len(group)
    followups = [press["followup"] for press in group if press["followup"]]
    followup = max(followups, key=lambda item: item["damage"]) if followups else None
    group_damage = sum(item["damage"] for item in followups)
    label = _label(blocked, "a move") if blocked["resolved"] else "a plus-on-block move"
    frames = f" ({on_block:+d} on block)" if type(on_block) is int else ""
    moves = _names(blocked)
    numbers = [count, group_damage, damage]
    if type(on_block) is int:
        numbers.append(on_block)
    if followup and followup.get("resolved"):
        moves += _names(followup)
        numbers.append(followup["damage"])
        text = f"After blocking {label}{frames} you pressed and ate {_label(followup, 'a hit')} for {followup['damage']}. Keep guarding instead."
    elif followup:
        text = f"After blocking {label}{frames} you pressed {times(count)} and got hit for {group_damage}. Keep guarding instead."
    else:
        text = f"After blocking {label}{frames} you pressed {times(count)}. {_bot(pack)} is plus there: keep guarding instead."
    return Candidate("after_block", text, "warn", damage, max(p, 0.1), moves, numbers,
                     {"blocked_move": {key: blocked.get(key) for key in ("name", "command", "on_block", "hit_level")},
                      "presses": count, "followup": {key: followup.get(key) for key in ("name", "command", "damage")} if followup else None,
                      "damage": group_damage, "habit_p": round(p, 2), "habit_n": n},
                     [c for press in group for c in press["citations"]][:2])


def sidestep_dir(pack):
    steps = [step for step in pack["sidesteps"] if step["hit"] and step["damage"] > 0 and step["resolved"] and step.get("tracking") != "homing"]
    if not steps:
        return None
    n, p = _rate(pack, "sidestep_dir", len(pack["sidesteps"]), len(pack["sidesteps"]))
    if n < MIN_N or p < 0.5:
        return None
    groups = {}
    for step in steps:
        groups.setdefault(step["move_id"], []).append(step)
    group = max(groups.values(), key=lambda items: (sum(i["damage"] for i in items), len(items)))
    top = group[0]
    count = len(group)
    damage = sum(step["damage"] for step in group)
    total = sum(step["damage"] for step in steps)
    label = _label(top, "a move")
    tracking = top.get("tracking") or ""
    moves = _names(top)
    punisher = pack_punisher(pack, top["move_id"])
    if tracking:
        answer = f"It tracks {tracking}, so step the other way."
    elif punisher:
        answer = f"Sidestep it, then punish with {punisher['command']}."
        moves += _names(punisher)
    else:
        answer = "Sidestep it, then punish."
    text = f"{label} hit you {times(count)} for {damage} while you stood still. {answer}"
    return Candidate("sidestep_dir", text, "warn", total, max(p, 0.1), moves, [count, damage, total],
                     {"opponent_move": {key: top.get(key) for key in ("name", "command", "hit_level", "tracking", "on_block")},
                      "hits_while_standing_still": count, "damage": damage, "punisher": punisher,
                      "habit_p": round(p, 2), "habit_n": n},
                     [c for step in group for c in step["citations"]][:2])


def pack_punisher(pack, move_id):
    for entry in pack["hits_taken"]:
        if entry.get("move_id") == move_id:
            return entry.get("punisher")
    return None


def neutral(pack):
    resolved = [entry for entry in pack["hits_taken"] if entry["resolved"] and entry["damage"] > 0]
    if not resolved:
        return None
    top = resolved[0]
    if top["count"] < 2:
        return None
    taken = sum(entry["damage"] for entry in pack["hits_taken"]) or top["damage"]
    share = top["damage"] / taken if taken else 0.0
    label = _label(top, "a move")
    level = top.get("hit_level") or "unknown"
    on_block = top.get("on_block")
    moves = _names(top)
    numbers = [top["count"], top["damage"]]
    punisher = top.get("punisher")
    if punisher:
        answer = f"Block it and punish with {punisher['command']}."
        moves += _names(punisher)
        numbers.append(on_block)
    elif type(on_block) is int and (on_block > 0 or top.get("plus_on_block")):
        answer = f"It is {on_block:+d} on block: block and hold guard."
        numbers.append(on_block)
    elif type(on_block) is int:
        answer = f"It is {on_block} on block: block it, do not press."
        numbers.append(on_block)
    else:
        answer = "Block it, then look for the next move."
    text = f"{label} hit you most, {times(top['count'])} for {top['damage']}. {answer}"
    return Candidate("neutral", text, "warn", top["damage"], max(share, 0.1), moves, numbers,
                     {"opponent_move": {key: top.get(key) for key in ("name", "command", "hit_level", "on_block", "distance", "tracking")},
                      "hits": top["count"], "damage": top["damage"], "counter_hits": top["counter_hits"],
                      "punisher": punisher, "share_of_damage": round(share, 2)},
                     top["citations"][:2])


def whiff_punish(pack):
    punished = [whiff for whiff in pack["whiffs"] if whiff["punished_by"] and whiff["resolved"]]
    if len(punished) < 2:
        return None
    groups = {}
    for whiff in punished:
        groups.setdefault(whiff["move_id"], []).append(whiff)
    group = max(groups.values(), key=lambda items: (sum(i["punished_by"]["damage"] for i in items), len(items)))
    top = group[0]
    count = len(group)
    damage = sum(whiff["punished_by"]["damage"] for whiff in group)
    total = sum(whiff["punished_by"]["damage"] for whiff in punished)
    label = _label(top, "a move")
    moves = _names(top)
    numbers = [count, damage, total, len(pack["whiffs"])]
    punisher = max((whiff["punished_by"] for whiff in group), key=lambda item: item["damage"])
    distance = top.get("distance")
    where = f" at {distance} range" if distance else ""
    if punisher.get("resolved"):
        moves += _names(punisher)
        text = f"You whiffed {label} {times(count)}{where} and ate {_label(punisher, 'a punish')} for {damage}. Close in before swinging."
    else:
        text = f"You whiffed {label} {times(count)}{where} and got punished for {damage}. Close in before swinging."
    rate = len(punished) / len(pack["whiffs"]) if pack["whiffs"] else 0.0
    return Candidate("whiff_punish", text, "warn", total, max(rate, 0.1), moves, numbers,
                     {"whiffed_move": {key: top.get(key) for key in ("name", "command", "distance")}, "whiffs": count,
                      "punished_by": {key: punisher.get(key) for key in ("name", "command", "damage")}, "damage": damage,
                      "whiffs_total": len(pack["whiffs"]), "punished_total": len(punished)},
                     [c for whiff in group for c in whiff["citations"]][:2])


def missed_punish(pack):
    missed = [item for item in pack["missed_punishes"] if item["punisher"] and item["blocked"]["resolved"]]
    if len(missed) < 2:
        return None
    groups = {}
    for item in missed:
        groups.setdefault(item["blocked"]["move_id"], []).append(item)
    group = max(groups.values(), key=lambda items: (len(items), -items[0]["blocked"].get("on_block", 0)))
    top = group[0]
    blocked, punisher = top["blocked"], top["punisher"]
    count = len(group)
    potential = (punisher.get("damage") or 0) * len(missed)
    on_block = blocked.get("on_block")
    label = _label(blocked, "a move")
    moves = _names(blocked, punisher)
    numbers = [count, len(missed), on_block]
    if punisher.get("damage"):
        numbers.append(punisher["damage"])
        text = f"You blocked {label} ({on_block} on block) {times(count)} without punishing. Punish with {punisher['command']} for {punisher['damage']}."
    else:
        text = f"You blocked {label} ({on_block} on block) {times(count)} without punishing. Punish with {punisher['command']}."
    return Candidate("missed_punish", text, "warn", potential, 1.0, moves, numbers,
                     {"blocked_move": {key: blocked.get(key) for key in ("name", "command", "on_block", "hit_level")},
                      "missed": count, "missed_total": len(missed), "attempted": sum(i["attempted"] for i in group),
                      "punisher": punisher},
                     [c for item in group for c in item["citations"]][:2])


BUILDERS = (low_defense, throw_break, after_block, sidestep_dir, neutral, whiff_punish, missed_punish)


def praise(pack):
    fixed = list(pack.get("newly_fixed", []))
    fixed += [habit["situation"] for habit in pack.get("habits", []) if habit.get("fixed") and habit["situation"] not in fixed]
    for situation in fixed:
        family = "after_block" if situation.startswith("after_block:") else situation
        label = FIXED_LABELS.get(family)
        if label:
            return Candidate(family, f"You've fixed your {label}. Keep practicing; I'll test it again later.", "praise",
                             detail={"newly_fixed": fixed})
    return None


def rank(pack, previous_topic=None):
    candidates = [candidate for candidate in (builder(pack) for builder in BUILDERS) if candidate is not None]
    covered = {candidate.detail.get("opponent_move", {}).get("command") for candidate in candidates
               if candidate.topic in {"low_defense", "sidestep_dir"}}
    candidates = [candidate for candidate in candidates
                  if candidate.topic != "neutral" or candidate.detail.get("opponent_move", {}).get("command") not in covered]
    candidates.sort(key=lambda candidate: (candidate.score, candidate.damage), reverse=True)
    if previous_topic and len(candidates) > 1:
        top_damage = max(candidate.damage for candidate in candidates)
        if not (candidates[0].topic == previous_topic and candidates[0].damage >= top_damage):
            candidates = ([c for c in candidates if c.topic != previous_topic]
                          + [c for c in candidates if c.topic == previous_topic])
    return candidates


def vocabulary(*characters):
    names = set()
    for character in characters:
        if not character:
            continue
        try:
            data = load_character(character)
        except (CharacterDataError, OSError, ValueError, KeyError):
            continue
        for move in list(data.moves) + list(data.throws):
            if move.get("name") and len(move["name"]) > 3:
                names.add(move["name"].lower())
    return names


def _allowed_numbers(candidate):
    allowed = set()
    for value in candidate.numbers:
        if type(value) is int:
            allowed.add(abs(value))
    return allowed


def validate_text(text, moves, candidate, vocab=()):
    if not isinstance(text, str) or not text.strip():
        return "empty"
    text = " ".join(text.split())
    if _words(text) > MAX_WORDS:
        return "too long"
    allowed = [value for value in candidate.moves if isinstance(value, str) and value]
    lowered_allowed = {value.lower() for value in allowed} | {normalize_command(value).lower() for value in allowed}
    for move in moves or []:
        if not isinstance(move, str) or (move.lower() not in lowered_allowed and normalize_command(move).lower() not in lowered_allowed):
            return f"unknown move {move!r}"
    residue = text.lower()
    for value in sorted(allowed, key=len, reverse=True):
        for form in {value.lower(), normalize_command(value).lower()}:
            residue = re.sub(r"(?<![a-z0-9+,~/])" + re.escape(form) + r"(?![a-z0-9]|[+,~/][1-4])", " ", residue)
    for name in vocab:
        if name in lowered_allowed:
            continue
        if re.search(r"(?<![\w])" + re.escape(name) + r"(?![\w])", residue):
            return f"ungrounded move name {name!r}"
    if COMMAND.search(residue):
        return "ungrounded command"
    numbers = _allowed_numbers(candidate)
    for match in NUMBER.findall(residue):
        try:
            value = abs(float(match))
        except ValueError:
            return f"bad number {match!r}"
        if value != int(value) or int(value) not in numbers:
            return f"ungrounded number {match}"
    return None


def topic_label(topic):
    return TOPIC_LABELS.get(topic, topic.replace("_", " "))
