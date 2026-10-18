import re

from replay.character_data import CharacterDataError, load_character, load_matchup, normalize_command


def compact(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())


def labeled_move(bot, query):
    resolution = bot.resolve_move(query)
    if resolution.status == "unique":
        return resolution.move
    if resolution.status == "ambiguous" or str(query).lower().startswith("0x"):
        return None
    matches = [move for move in bot.moves if compact(move["command"]) == compact(str(query))]
    return matches[0] if len(matches) == 1 else None


def specific_tip(summary, habit):
    try:
        bot = load_character(summary.get("bot_character"))
        notes = load_matchup(summary.get("human_character"), bot.name)
        situation = habit["situation"]
        move = None
        if situation.startswith("after_block:"):
            move = labeled_move(bot, situation.split(":", 1)[1])
        else:
            for moment in sorted(summary["biggest_moments"], key=lambda value: value.get("damage", 0), reverse=True):
                if moment.get("situation") != situation:
                    continue
                if "actor" in moment and (type(moment["actor"]) is not int or moment["actor"] != 1 - summary["human_slot"]):
                    continue
                expected = {"hit", "counter_hit"} if situation == "low_defense" else {"throw"}
                if moment["kind"] not in expected:
                    continue
                resolution = bot.resolve_move_id(moment.get("move_id"))
                if resolution.status == "unique":
                    move = resolution.move
                    break
        if move is None:
            return None
        name, count = bot.label(move), habit["n"]
        if situation == "low_defense" and move.get("hit_level") in {"low", "special_low"}:
            return (f"Low-defense trouble appeared across {count} observations. Practice crouch-blocking {name}, then returning to standing guard.")
        if situation.startswith("after_block:"):
            plus_rows = notes.tables.get("Moves that leave them plus on block (do not press buttons)", []) if notes else []
            plus = any(normalize_command(row.get("Move", "")) == normalize_command(move["command"]) for row in plus_rows)
            if plus and type(move.get("on_block")) is int and move["on_block"] >= 0:
                return f"After blocking {name}, keep guarding; the opponent has advantage. Wait before pressing again."
            return f"After blocking {name}, practice guarding before pressing. Punish timing and range still need checking."
        if situation == "throw_break":
            break_input = bot.throw_break(move["command"])
            if break_input in {"1", "2", "1+2", "1/2"}:
                return f"Recognize {name} and practice the {break_input} break input."
    except (CharacterDataError, OSError, KeyError, ValueError, TypeError):
        return None
    return None
