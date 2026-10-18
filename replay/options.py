from replay.character_data import (
    CharacterDataError,
    load_character,
    normalize_character,
)

MAX_OPTIONS = 6
PUNISH_DISTANCES = ("point_blank", "close")
MIN_PUNISH_GAP = 10

ROLE_KINDS = {
    "human_hit", "human_landed_hit", "human_attack_blocked", "human_block", "human_whiff",
    "opponent_whiff", "human_thrown", "human_throw_attempt", "human_throw_break",
    "opponent_throw_break", "human_knockdown", "opponent_knockdown", "human_decision",
    "unattributed_event",
}

GENERAL_LIMITATION = "Options are candidates drawn from the human's character data; none is established as better than what the player did."

AFTER_BLOCK_ORDER = ("press_poke", "block_high", "block_low", "backdash", "sidestep_left", "sidestep_right", "duck")
HIT_ORDER = {
    "low": ("block_low", "sidestep_left", "sidestep_right", "backdash"),
    "special_low": ("block_low", "sidestep_left", "sidestep_right", "backdash"),
    "high": ("duck", "block_high", "backdash", "sidestep_left", "sidestep_right"),
    "mid": ("block_high", "sidestep_left", "sidestep_right", "backdash"),
}
DEFENSIVE_ORDER = ("block_high", "block_low", "duck", "backdash", "sidestep_left", "sidestep_right")
NEUTRAL_ORDER = ("poke", "mid", "low", "tracking", "backdash", "wait")
WHIFF_ORDER = ("poke", "mid_launcher", "wait")
SITUATION_PREFIXES = (
    ("after_block", "after_block"),
    ("throw_break", "throw"),
    ("low_defense", "low_defense"),
    ("sidestep_dir", "sidestep_dir"),
)
OKI_CATEGORIES = ("mid", "low", "throw", "wait")
ATTACK_BLOCKED_CATEGORIES = ("poke", "throw", "low", "mid")


def _title(text):
    return text.replace("_", " ").replace(":", " ").capitalize()


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _derive_role(kind, human, actor, target):
    if human not in (0, 1):
        return "unattributed_event"
    if kind == "decision_point":
        return "human_decision" if actor == human else ("unattributed_event" if actor is None else None)
    if kind in ("hit", "counter_hit"):
        return "human_hit" if target == human else ("human_landed_hit" if actor == human else "unattributed_event")
    if kind == "block":
        return "human_attack_blocked" if actor == human else ("human_block" if target == human else "unattributed_event")
    if kind == "whiff":
        return "human_whiff" if actor == human else ("opponent_whiff" if actor is not None else "unattributed_event")
    if kind == "throw":
        return "human_thrown" if target == human else ("human_throw_attempt" if actor == human else "unattributed_event")
    if kind == "throw_break":
        return "human_throw_break" if actor == human else ("opponent_throw_break" if target == human else "unattributed_event")
    if kind == "knockdown":
        return "human_knockdown" if target == human else ("opponent_knockdown" if actor == human else "unattributed_event")
    return None


def _facts(moment):
    evidence = moment.get("evidence")
    record = None
    if isinstance(evidence, list) and evidence and isinstance(evidence[0], dict):
        record = evidence[0].get("record")
    if not isinstance(record, dict):
        record = moment if moment.get("t") == "event" else {}
    context = moment.get("context") if isinstance(moment.get("context"), dict) else {}
    human_context = context.get("human") if isinstance(context.get("human"), dict) else {}
    opponent_context = context.get("opponent") if isinstance(context.get("opponent"), dict) else {}
    kind = moment.get("kind")
    human_slot = moment.get("human_slot")
    actor = _int(moment.get("actor", record.get("actor")))
    target = _int(moment.get("target", record.get("target")))
    if kind in ROLE_KINDS:
        role = kind
    else:
        role = _derive_role(moment.get("event_kind") or kind or record.get("kind"), human_slot, actor, target)
    advantage = None
    for candidate in (moment.get("frame_advantage"), moment.get("recorded_frame_advantage"), record.get("frame_advantage")):
        if _int(candidate) is not None:
            advantage = candidate
            break
    detail = record.get("detail") if isinstance(record.get("detail"), dict) else moment.get("detail")
    return {
        "role": role,
        "move_id": moment.get("move_id", record.get("move_id")),
        "hit_level": moment.get("hit_level", record.get("hit_level")),
        "advantage": advantage,
        "detail": detail if isinstance(detail, dict) else {},
        "distance_bucket": moment.get("distance_bucket", context.get("distance_bucket")),
        "human_character": moment.get("human_character", human_context.get("character")),
        "opponent_character": moment.get("opponent_character", opponent_context.get("character")),
        "situation": moment.get("situation", record.get("situation")),
    }


def _option(option_id, name, command, description):
    return {"id": option_id, "name": name, "command": command, "description": description}


def _valid_command(human, command):
    return command in human.by_command or command in human.throw_by_command


def _entry_option(human, entry, extra=""):
    option_id = entry["id"]
    suffix = f" {extra}" if extra else ""
    if entry.get("moves"):
        for command in entry["moves"]:
            if command in human.by_command:
                move = human.by_command[command]
                return _option(option_id, human.label(move), command, entry["description"] + suffix)
        return None
    if entry.get("input"):
        return _option(option_id, _title(option_id), entry["input"], entry["description"] + suffix)
    return None


def _menu(human, key):
    points = human.options.get("decision_points", {})
    return {entry["id"]: entry for entry in points.get(key, {}).get("options", [])}


def _ordered(human, key, order, skip=()):
    menu = _menu(human, key)
    options = []
    for option_id in order:
        entry = menu.get(option_id)
        if entry is None or option_id in skip:
            continue
        built = _entry_option(human, entry)
        if built:
            options.append(built)
    return options


def _category_options(human, situation, categories, prefix):
    options_by_name = human.options.get("situations", {}).get(situation, {}).get("options", {})
    descriptions = human.options.get("abstract_options", {})
    built = []
    for category in categories:
        commands = options_by_name.get(category)
        if not isinstance(commands, list):
            continue
        for command in commands:
            if command in human.by_command or command in human.throw_by_command:
                move = human.by_command.get(command)
                name = human.label(move) if move else command
                built.append(_option(f"{prefix}_{category}", name, command,
                                     descriptions.get(category, _title(category))))
                break
            if category in ("wait", "backdash", "block") and command in human.options.get("inputs", {}):
                built.append(_option(f"{prefix}_{category}", _title(category),
                                     human.options["inputs"][command], descriptions.get(category, _title(category))))
                break
    return built


def _opponent(facts, limitations):
    character = facts["opponent_character"]
    if normalize_character(character) is None:
        limitations.append("The opponent's character is not known, so the opponent's move cannot be named.")
        return None
    try:
        return load_character(character)
    except CharacterDataError as error:
        limitations.append(str(error))
        return None


def _resolve_opponent_move(opponent, facts, limitations):
    if opponent is None:
        return None
    if facts["move_id"] is None:
        limitations.append("The event has no move ID, so the opponent's move is not named.")
        return None
    resolution = opponent.resolve_move_id(facts["move_id"])
    if not resolution.found:
        limitations.append(f"Opponent move not named: {resolution.reason}.")
        return None
    return resolution.move


def _punish_options(human, facts, opponent_move, limitations):
    advantage = facts["advantage"]
    if advantage is None:
        limitations.append("No recorded frame advantage, so a punish is not offered.")
        return []
    if advantage > -MIN_PUNISH_GAP:
        limitations.append(f"Recorded frame advantage {advantage} leaves no guaranteed punish window of {MIN_PUNISH_GAP} frames; no punish is offered.")
        return []
    if facts["detail"].get("string_continued") is True:
        limitations.append("The opponent's string continued, so a punish is not established.")
        return []
    if facts["distance_bucket"] not in PUNISH_DISTANCES:
        limitations.append(f"Distance ({facts['distance_bucket'] or 'unknown'}) does not establish that a punish reaches; no punish is offered.")
        return []
    if opponent_move is not None and opponent_move.get("on_block") is not None and abs(opponent_move["on_block"] - advantage) > 1:
        limitations.append(f"Recorded frame advantage {advantage} disagrees with {opponent_move['command']} on block ({opponent_move['on_block']}); no punish is offered.")
        return []
    raw = (opponent_move or {}).get("on_block_raw") or ""
    crouching = facts["hit_level"] in ("low", "special_low") or raw.endswith("c")
    entries = human.punish_tier(advantage, crouching=crouching)
    if not entries:
        limitations.append("No punisher is listed for this frame gap; no punish is offered.")
        return []
    source = "against the blocked move"
    if opponent_move:
        named = f"{opponent_move['name']} ({opponent_move['command']})" if opponent_move.get("name") else opponent_move["command"]
        source = f"after {named}"
    options, seen = [], set()
    for entry in entries:
        command = entry["command"]
        if command in seen or command not in human.by_command or entry.get("difficulty") == "hard":
            continue
        seen.add(command)
        move = human.by_command[command]
        kind = "launcher" if entry.get("launcher") else "punisher"
        options.append(_option(
            f"punish_{len(options) + 1}", human.label(move), command,
            f"{kind} i{entry['startup']} {source}: recorded frame advantage {advantage} and close range give a window of at least {-advantage} frames."))
        if len(options) == 2:
            break
    if options:
        limitations.append("Punish options rely on recorded frame advantage, distance bucket and character frame data; the player's actual input timing was not checked.")
    return options


def _after_block(human, facts, opponent, limitations, allow_punish):
    options = []
    if allow_punish:
        opponent_move = _resolve_opponent_move(opponent, facts, limitations)
        options.extend(_punish_options(human, facts, opponent_move, limitations))
    else:
        limitations.append("No frame advantage was evaluated for this decision label; no punish is offered.")
    options.extend(_ordered(human, "after_block", AFTER_BLOCK_ORDER))
    return options


def _thrown(human, facts, opponent, limitations):
    options = _ordered(human, "throw", ("break_1", "break_2", "break_1+2", "no_break"))
    move = _resolve_opponent_move(opponent, facts, limitations)
    if move is None:
        limitations.append("The break input for this throw is not established.")
        return options
    expected = opponent.throw_break(move["command"])
    if expected is None:
        limitations.append(f"The break input for {move['command']} is not stated in the character data.")
        return options
    accepted = {"1": ("break_1",), "2": ("break_2",), "1+2": ("break_1+2",), "1/2": ("break_1", "break_2")}.get(expected, ())
    for option in options:
        if option["id"] in accepted:
            option["description"] += f" The character data lists break {expected} for {move['command']}."
    return options


def _knocked_down(human):
    return _ordered(human, "wakeup", ("block_high", "block_low", "backdash", "poke", "throw"))


def _attack_blocked(human, facts, limitations):
    options = _category_options(human, "even_close", ATTACK_BLOCKED_CATEGORIES, "alt")
    resolution = human.resolve_move_id(facts["move_id"]) if facts["move_id"] is not None else None
    unsafe = resolution is not None and resolution.found and (resolution.move.get("on_block") or 0) <= -MIN_PUNISH_GAP
    if unsafe:
        limitations.append(f"The blocked move {resolution.move['command']} is {resolution.move['on_block']} on block in the character data.")
        options.extend(_category_options(human, "minus_close", ("safe",), "alt")[:1])
    else:
        options.extend(_category_options(human, "minus_close", ("backdash",), "alt")[:1])
        if not any(option["command"] == "b,b" for option in options):
            options.extend(_ordered(human, "neutral", ("backdash",)))
    return options


def _hit(human, facts, limitations):
    if facts["hit_level"] == "throw":
        return _thrown(human, facts, None, limitations)
    order = HIT_ORDER.get(facts["hit_level"], DEFENSIVE_ORDER)
    limitations.append("Whether any listed defence would have avoided the hit is not established.")
    return _ordered(human, "after_block", order)


def _decision(human, facts, opponent, limitations):
    situation = facts["situation"] or ""
    for prefix, key in SITUATION_PREFIXES:
        if situation.startswith(prefix):
            if key == "after_block":
                return _after_block(human, facts, opponent, limitations, False)
            if key == "throw":
                return _thrown(human, facts, None, limitations)
            if key == "low_defense":
                return _ordered(human, "after_block", ("block_low", "duck", "block_high", "backdash"))
            return _ordered(human, "after_block", ("sidestep_left", "sidestep_right", "backdash", "block_high"))
    limitations.append("The decision label does not name a situation; neutral options are offered.")
    return _ordered(human, "neutral", NEUTRAL_ORDER)


def generate_options(character, moment):
    limitations = [GENERAL_LIMITATION]
    try:
        human = load_character(character)
    except CharacterDataError as error:
        return {"options": [], "limitations": [str(error)]}
    if not isinstance(moment, dict):
        limitations.append("The moment is not an object; no options were generated.")
        return {"options": [], "limitations": limitations}
    facts = _facts(moment)
    role = facts["role"]
    stated = normalize_character(facts["human_character"])
    if stated is not None and stated != human.name:
        limitations.append(f"The moment lists {stated} as the human's character; options use {human.name}.")
    needs_opponent = role in ("human_block", "human_thrown", "human_decision", "human_hit")
    opponent = _opponent(facts, limitations) if needs_opponent else None
    if role == "human_block":
        options = _after_block(human, facts, opponent, limitations, True)
    elif role == "human_hit":
        options = _hit(human, facts, limitations)
    elif role == "human_thrown":
        options = _thrown(human, facts, opponent, limitations)
    elif role == "human_knockdown":
        options = _knocked_down(human)
    elif role == "opponent_knockdown":
        options = _category_options(human, "opp_knockdown", OKI_CATEGORIES, "oki")
        limitations.append("Which option connects against the opponent's wakeup is not established.")
    elif role == "human_attack_blocked":
        options = _attack_blocked(human, facts, limitations)
    elif role == "opponent_whiff":
        options = _ordered(human, "opp_whiff", WHIFF_ORDER)
        limitations.append("Whiff-punish range and timing are not established by the recording or character data; no punish is offered.")
    elif role == "human_decision":
        options = _decision(human, facts, opponent, limitations)
    elif role in ("human_whiff", "human_landed_hit", "human_throw_attempt", "human_throw_break", "opponent_throw_break"):
        options = _ordered(human, "neutral", NEUTRAL_ORDER)
    else:
        options = []
        limitations.append("The human's role in this moment cannot be established; no options were generated.")
    seen_ids, seen_commands, unique = set(), set(), []
    for option in options:
        if option["id"] in seen_ids or option["command"] in seen_commands:
            continue
        seen_ids.add(option["id"])
        seen_commands.add(option["command"])
        unique.append(option)
    deduped = list(dict.fromkeys(limitations))
    return {"options": unique[:MAX_OPTIONS], "limitations": deduped}
