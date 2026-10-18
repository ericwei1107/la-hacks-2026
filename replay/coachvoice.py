from replay import tips
from replay.character_data import CharacterDataError, load_character

GENERIC_FIX = {
    "low_defense": "Hold down-back when {bot} gets close so the lows land on your guard, then stand back up.",
    "throw_break": "When {bot} grabs you, press the break for that throw as the grab starts.",
    "after_block": "After you block, hold guard for a beat before pressing, and punish only what is unsafe.",
    "sidestep_dir": "Sidestep as {bot}'s move starts, then punish; if it tracks, step the other way.",
}
GOOD_HABIT = {
    ("low_defense", "blocked"): "You blocked these lows. Keep that guard and punish the unsafe ones.",
    ("low_defense", "low_parry"): "You parried these lows. Keep it up and follow with a combo.",
    ("throw_break", "break_1"): "You broke these throws with 1. Keep watching the grabbing hand.",
    ("throw_break", "break_2"): "You broke these throws with 2. Keep watching the grabbing hand.",
    ("throw_break", "break_12"): "You broke these throws with 1+2. Keep watching the grabbing hand.",
    ("after_block", "block_high"): "You held guard after blocking. Now look for the punish when {bot} is unsafe.",
    ("after_block", "block_low"): "You held low guard after blocking. Now stand up for the mids and punish what is unsafe.",
    ("after_block", "backdash"): "You backed off after blocking. Good; now punish the moves that are unsafe.",
    ("after_block", "throw"): "You answered blocked moves with throws. Mix in the punisher when {bot} is minus.",
    ("sidestep_dir", "left"): "You stepped left there. Keep stepping, then punish the whiff.",
    ("sidestep_dir", "right"): "You stepped right there. Keep stepping, then punish the whiff.",
}
ACTION_PHRASES = {
    ("low_defense", "hit"): "got hit by the low", ("low_defense", "blocked"): "blocked the low",
    ("low_defense", "jumped"): "jumped over the low", ("low_defense", "low_parry"): "parried the low",
    ("throw_break", "none"): "did not press a break", ("throw_break", "break_1"): "pressed 1",
    ("throw_break", "break_2"): "pressed 2", ("throw_break", "break_12"): "pressed 1+2",
    ("after_block", "press"): "pressed a button", ("after_block", "block_high"): "held guard",
    ("after_block", "block_low"): "held low guard", ("after_block", "duck"): "ducked",
    ("after_block", "backdash"): "backed off", ("after_block", "ss_left"): "stepped left",
    ("after_block", "ss_right"): "stepped right", ("after_block", "throw"): "went for a throw",
    ("after_block", "none"): "did nothing", ("sidestep_dir", "none"): "stood still",
    ("sidestep_dir", "left"): "stepped left", ("sidestep_dir", "right"): "stepped right",
}
DRILLS = {
    "low_defense": "In Practice, set the dummy to that low and crouch-block it until it is automatic, then stand back up.",
    "throw_break": "In Practice, set the dummy to that throw and break it ten times in a row.",
    "after_block": "In Practice, block that move and hold guard through the follow-up before pressing.",
    "sidestep_dir": "In Practice, sidestep that move as it starts, then punish.",
    "neutral": "In Practice, set the dummy to that move and block it on reaction until it is automatic.",
    "whiff_punish": "In Practice, hold your ground until the opponent whiffs, then punish.",
    "missed_punish": "In Practice, block that move on repeat and punish it every time.",
}
SITUATION_PHRASES = {
    "low_defense": "when a low came", "throw_break": "when you were grabbed",
    "after_block": "right after blocking", "sidestep_dir": "when you could have stepped",
}


def family(situation):
    return "after_block" if str(situation).startswith("after_block") else str(situation)


def bot_label(pack):
    return str((pack or {}).get("bot_character") or "the opponent").replace("_", " ").title()


def topic_for(situation, action):
    base = family(situation)
    if base == "low_defense":
        return "low_defense" if action == "hit" else None
    if base == "throw_break":
        return "throw_break" if action not in GOOD_HABIT_ACTIONS else None
    if base == "after_block":
        return "after_block" if action == "press" else None
    if base == "sidestep_dir":
        return "sidestep_dir" if action == "none" else None
    return None


GOOD_HABIT_ACTIONS = {"break_1", "break_2", "break_12"}


def action_phrase(situation, action):
    return ACTION_PHRASES.get((family(situation), action)) or f"chose {str(action).replace('_', ' ')}"


def situation_phrase(situation):
    return SITUATION_PHRASES.get(family(situation)) or f"in {str(situation).replace('_', ' ').replace(':', ' ')} spots"


def ranked(pack):
    if not pack:
        return []
    try:
        return tips.rank(pack)
    except (KeyError, TypeError, ValueError):
        return []


def candidate_for(pack, topic, candidates=None):
    for candidate in (candidates if candidates is not None else ranked(pack)):
        if candidate.topic == topic:
            return candidate
    return None


def habit_fix(pack, situation, action, candidates=None):
    bot = bot_label(pack)
    good = GOOD_HABIT.get((family(situation), action))
    if good:
        return good.format(bot=bot)
    topic = topic_for(situation, action)
    if topic is None:
        return f"{situation_phrase(situation).capitalize()} you {action_phrase(situation, action)}. Watch those spots and pick the answer that keeps your turn."
    candidate = candidate_for(pack, topic, candidates)
    if candidate is not None:
        return candidate.text
    return GENERIC_FIX[topic].format(bot=bot)


def _match(rows, round_number, frame):
    for row in rows:
        if row.get("round") == round_number and row.get("frame") == frame:
            return row
    return None


def point_cost(pack, round_number, frame, situation, action, detail):
    detail = detail or {}
    base = family(situation)
    if base == "low_defense":
        return detail.get("damage") if action == "hit" and type(detail.get("damage")) is int else 0
    if not pack:
        return 0
    if base == "throw_break":
        start = detail.get("start_frame", frame)
        throw = _match(pack.get("throws", []), round_number, start)
        return throw["damage"] if throw and not throw["broken"] else 0
    if base == "after_block" and action == "press":
        press = _match(pack.get("presses", []), round_number, frame)
        if press and press["followup"] and type(press["human_advantage"]) is int and press["human_advantage"] <= 0:
            return press["followup"]["damage"]
        return 0
    if base == "sidestep_dir" and action == "none":
        step = _match(pack.get("sidesteps", []), round_number, frame)
        return step["damage"] if step else 0
    return 0


def positives(pack):
    out = []
    if not pack:
        return out
    bot = bot_label(pack)
    throws = pack.get("throws", [])
    broken = [throw for throw in throws if throw["broken"]]
    if broken:
        named = next((throw for throw in broken if throw.get("name")), None)
        detail = f", including {named['name']} ({named['command']})" if named else ""
        out.append((f"You broke {len(broken)} of {len(throws)} throws{detail}.",
                    [c for throw in broken for c in throw["citations"]][:2]))
    lows = pack.get("low_decisions", {})
    blocked = sum(entry["blocked"] for entry in lows.values())
    total = sum(entry["hit"] + entry["blocked"] + entry["other"] for entry in lows.values())
    if blocked:
        cites = [c for entry in lows.values() for c in entry["citations"]][:2]
        out.append((f"You blocked {blocked} of {total} lows {bot} threw at you.", cites))
    landed = pack.get("punishes_landed", [])
    if landed:
        named = [item for item in landed if item["blocked"].get("command") and item["punish"].get("command")]
        detail = ""
        if named:
            best = max(named, key=lambda item: item["punish"]["damage"])
            name = best["blocked"].get("name") or best["blocked"]["command"]
            punish = best["punish"].get("name") or best["punish"]["command"]
            detail = f", like {name} with {punish} for {best['punish']['damage']}"
        out.append((f"You punished {len(landed)} unsafe {'move' if len(landed) == 1 else 'moves'}{detail}.",
                    [c for item in landed for c in item["citations"]][:2]))
    whiffs = pack.get("whiff_punishes_landed", [])
    if whiffs:
        out.append((f"You punished {len(whiffs)} of {bot}'s whiffs.", [c for item in whiffs for c in item["citations"]][:2]))
    return out


def _round_counts(pack, topic):
    counts = {}
    for number, sub in sorted(pack.get("per_round", {}).items()):
        if topic == "low_defense":
            counts[number] = sum(entry["count"] for entry in sub["hits_taken"] if entry.get("hit_level") in {"low", "special_low"})
        elif topic == "throw_break":
            counts[number] = sum(1 for throw in sub["throws"] if not throw["broken"])
        elif topic == "after_block":
            counts[number] = sum(1 for press in sub["presses"] if type(press["human_advantage"]) is int and press["human_advantage"] <= 0)
        elif topic == "sidestep_dir":
            counts[number] = sum(1 for step in sub["sidesteps"] if step["hit"])
        else:
            counts[number] = sum(entry["damage"] for entry in sub["hits_taken"]) + sum(throw["damage"] for throw in sub["throws"])
    return counts


def _trend(values):
    if len(values) < 2:
        return ""
    earlier = sum(values[:-1]) / (len(values) - 1)
    last = values[-1]
    if last < earlier:
        return "trending the right way"
    if last > earlier:
        return "trending up, so fix that first"
    return "about the same each round"


def progression(pack, situation=""):
    if not pack or len(pack.get("per_round", {})) < 2:
        return None
    bot = bot_label(pack)
    wanted = family(situation) if situation else ""
    lines = []
    damage = {number: sub.get("damage_taken") if type(sub.get("damage_taken")) is int else None
              for number, sub in sorted(pack["per_round"].items())}
    if any(value is None for value in damage.values()):
        damage = _round_counts(pack, "damage")
    if not wanted:
        lines.append(f"Round by round you took {', '.join(str(v) for v in damage.values())} damage.")
    labels = {"low_defense": f"{bot}'s lows hit you", "throw_break": "throws landed on you",
              "after_block": "you pressed into a plus move", "sidestep_dir": "you stood still and got hit"}
    for topic, label in labels.items():
        if wanted and topic != wanted:
            continue
        counts = _round_counts(pack, topic)
        values = list(counts.values())
        if not any(values):
            continue
        lines.append(f"{label[0].upper() + label[1:]} {', '.join(str(v) for v in values)} times round by round, {_trend(values)}.")
    if not lines:
        return None
    return " ".join(lines)


def _route(data, command):
    launchers = data.combos.get("launchers", {}) if isinstance(data.combos, dict) else {}
    routes = launchers.get(command)
    route = routes.get("reliable") if isinstance(routes, dict) else None
    if isinstance(route, dict) and route.get("route"):
        return route
    bnb = data.combos.get("bnb", {}) if isinstance(data.combos, dict) else {}
    regular = bnb.get("regular_launch")
    return regular if isinstance(regular, dict) and regular.get("route") else None


def _route_text(route):
    damage = f" for {route['dmg']}" if type(route.get("dmg")) is int else ""
    return f"{route['route']}{damage}"


def combos(character, pack=None):
    try:
        data = load_character(character)
    except (CharacterDataError, OSError, ValueError, KeyError):
        return []
    launchers = data.combos.get("launchers", {}) if isinstance(data.combos, dict) else {}
    label = str(data.name).replace("_", " ").title()
    facts = []
    openings = []
    seen = set()
    for candidate in ranked(pack):
        punisher = candidate.detail.get("punisher")
        move = candidate.detail.get("opponent_move") or candidate.detail.get("blocked_move")
        if not punisher or not punisher.get("launcher") or not move or not move.get("command") or punisher["command"] in seen:
            continue
        route = _route(data, punisher["command"])
        if route is None:
            continue
        seen.add(punisher["command"])
        name = f"{move['name']} ({move['command']})" if move.get("name") else move["command"]
        on_block = f" at {move['on_block']} on block" if type(move.get("on_block")) is int else ""
        openings.append(f"Block {name}{on_block}, launch with {punisher['command']}, then {_route_text(route)}.")
    if openings:
        facts.append(f"Your best launch chances this set, from the character data: " + " ".join(openings[:2])
                     + " Verify the routes in Practice before relying on them.")
    routes = []
    for command, entry in launchers.items():
        route = entry.get("reliable") if isinstance(entry, dict) else None
        if not isinstance(route, dict) or not route.get("route") or command in seen:
            continue
        move = data.by_command.get(command)
        name = f"{move['name']} ({command})" if move and move.get("name") else command
        routes.append(f"After {name}: {_route_text(route)}.")
    if routes:
        facts.append(f"{label}'s reliable combos from the character data. " + " ".join(routes[:3])
                     + (" Verify the routes in Practice before relying on them." if not openings else ""))
    return facts
