import copy
import json
from pathlib import Path

from game.notation import NotationError, compile_notation

ROOT = Path(__file__).resolve().parent.parent
FALLBACK_PATH = Path(__file__).resolve().parent / "options_fallback.json"
CLASSES = ("mid", "low", "throw", "launcher", "backdash", "sidestep", "approach", "wait")
ATTACK_CLASSES = ("mid", "low", "throw", "launcher")
MOVEMENT_CLASSES = ("backdash", "sidestep", "approach", "wait")
MOVEMENT_SETS = {"basic": 0, "sidestep": 1, "character": 2, "full": 3}
BUCKETS = ("point_blank", "close", "mid", "far", "very_far")
REQUIRED = ("mid", "low", "throw")
DEFAULT_RANGES = {"mid": ("point_blank", "close"), "low": ("point_blank", "close"), "throw": ("point_blank", "close"),
                  "launcher": ("point_blank", "close")}
GARRETT_CLASSES = {
    "mid": ("mid", "poke", "frame_trap", "safe", "plus_pressure", "tracking"),
    "low": ("low",),
    "throw": ("throw",),
    "launcher": ("mid_launcher",),
}
GARRETT_MOVEMENT = {"approach": "approach", "backdash": "backdash", "sidestep_left": "sidestep", "sidestep_right": "sidestep",
                    "wait": "wait", "block": "wait"}
NOTATION_FIXES = {"n": "B", "block": "B", "f,n,d,df": "f,n,d,df,f,n,d,df"}
MERGE_FROM_FALLBACK = ("throw", "approach", "sidestep", "backdash", "wait")
NOT_MID = ("low", "special_low", "throw")
GARRETT_RANGES = {"plus_close": ("point_blank", "close"), "even_close": ("point_blank", "close"), "minus_close": ("point_blank", "close"),
                  "minus_big": ("point_blank", "close"), "neutral_mid": ("mid",), "neutral_far": ("far",),
                  "opp_knockdown": ("point_blank", "close"), "opp_wall": ("point_blank", "close"), "opp_whiff": ("close", "mid")}
SIDESTEP_INPUTS = {"ssl": "u", "ssr": "d"}
ELECTRIC_SUFFIX = " (electric)"
POSITION_DECAY = 0.25


def load_fallback(path=FALLBACK_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def default_plan(path=FALLBACK_PATH):
    return copy.deepcopy(load_fallback(path)["default_plan"])


def parses(notation):
    try:
        compile_notation(notation)
        return True
    except NotationError:
        return False


def normalize_entry(entry, cls):
    out = dict(entry)
    out.setdefault("weight", 1.0)
    out.setdefault("tags", [])
    out.setdefault("movement_set", "sidestep" if cls == "sidestep" else "basic")
    out.setdefault("ranges", list(DEFAULT_RANGES.get(cls, BUCKETS)))
    if cls in ATTACK_CLASSES:
        out.setdefault("hit_level", "throw" if cls == "throw" else "mid")
        out.setdefault("move_id", None)
        ids = [i for i in (out.get("move_ids") or []) if i] + ([out["move_id"]] if out.get("move_id") else [])
        out["move_ids"] = sorted({str(i).lower() for i in ids})
        out.setdefault("startup", None)
        out.setdefault("on_block", None)
    if cls == "throw":
        out.setdefault("break", None)
    return out


def executable(notation):
    return parses(notation) and not notation.lower().startswith("ws")


def normalize_table(table):
    classes = {cls: [normalize_entry(e, cls) for e in table.get("classes", {}).get(cls, []) if executable(e["notation"])] for cls in CLASSES}
    names = {k.lower(): v for k, v in table.get("move_names", {}).items()}
    return {"classes": classes, "move_names": names}


def first_level(level):
    if isinstance(level, list):
        return level[0] if level else "mid"
    return level or "mid"


def movement_notation(command, inputs):
    text = inputs.get(command, command)
    text = SIDESTEP_INPUTS.get(text, text)
    return NOTATION_FIXES.get(text, text)


def attack_entry(command, notation, move, his_cls, position, breaks):
    tags = []
    if move.get("tracking") == "homing":
        tags.append("homing")
    if "launcher" in move.get("tags", []):
        tags.append("launcher")
    if his_cls == "poke":
        tags.append("poke")
    if "f,n,d" in notation:
        tags.append("wavedash")
    ids = move.get("move_ids") or []
    entry = {
        "notation": notation,
        "move_id": move.get("move_id") or (ids[-1] if ids else None),
        "move_ids": list(ids),
        "hit_level": first_level(move.get("hit_level")),
        "startup": move.get("startup"),
        "on_block": move.get("on_block"),
        "weight": round(1.0 / (1.0 + POSITION_DECAY * position), 3),
        "ranges": set(),
        "tags": tags,
        "movement_set": "character" if "f,n,d" in notation else "basic",
    }
    if entry["hit_level"] == "throw":
        entry["break"] = breaks.get(command)
    return entry


def from_characters(options, moves, throws=None, fallback=None):
    by_command = {m["command"]: m for m in moves.get("moves", [])}
    breaks = {t["command"]: t.get("break") for t in (throws or {}).get("throws", [])}
    inputs = options.get("inputs", {})
    collected = {cls: {} for cls in CLASSES}
    for sit_name, sit in options.get("situations", {}).items():
        ranges = GARRETT_RANGES.get(sit_name, ("point_blank", "close"))
        for his_cls, commands in sit.get("options", {}).items():
            if not isinstance(commands, list):
                continue
            if his_cls in GARRETT_MOVEMENT:
                ours = GARRETT_MOVEMENT[his_cls]
                for command in commands:
                    notation = movement_notation(command, inputs)
                    entry = collected[ours].setdefault(notation, {"notation": notation, "weight": 1.0, "tags": [], "ranges": set()})
                    entry["ranges"].update(BUCKETS)
                    if "f,n,d" in notation:
                        entry["movement_set"] = "character"
                        entry["tags"] = ["wavedash"]
                continue
            ours = next((c for c, his in GARRETT_CLASSES.items() if his_cls in his), None)
            if ours is None:
                continue
            for i, command in enumerate(commands):
                notation = command.replace(ELECTRIC_SUFFIX, "")
                move = by_command.get(command) or by_command.get(notation) or {}
                level = first_level(move.get("hit_level"))
                target = ours
                if ours == "mid" and level in NOT_MID:
                    target = "throw" if level == "throw" else "low"
                if target in ("mid", "low") and "launcher" in move.get("tags", []) and level not in ("low", "special_low"):
                    target = "launcher"
                entry = collected[target].get(notation)
                if entry is None:
                    entry = attack_entry(command, notation, move, his_cls, i, breaks)
                    collected[target][notation] = entry
                entry["ranges"].update(ranges)
    classes = {}
    for cls, entries in collected.items():
        rows = []
        for e in entries.values():
            e = dict(e)
            e["ranges"] = [b for b in BUCKETS if b in e["ranges"]] or list(DEFAULT_RANGES.get(cls, BUCKETS))
            rows.append(e)
        classes[cls] = rows
    for cls in MERGE_FROM_FALLBACK:
        have = {e["notation"] for e in classes[cls]}
        for e in (fallback or {}).get("classes", {}).get(cls, []):
            if e["notation"] not in have:
                classes[cls].append(dict(e))
    known = {}
    for cls in ATTACK_CLASSES:
        for e in (fallback or {}).get("classes", {}).get(cls, []):
            known[e["notation"].lower()] = [i for i in (e.get("move_ids") or []) if i] + ([e["move_id"]] if e.get("move_id") else [])
    for cls in ATTACK_CLASSES:
        for e in classes[cls]:
            extra = known.get(e["notation"].lower(), [])
            e["move_ids"] = list(e.get("move_ids") or []) + extra
            if not e.get("move_id") and extra:
                e["move_id"] = extra[-1]
    names = {}
    for m in moves.get("moves", []):
        for mid in m.get("move_ids") or []:
            names.setdefault(mid.lower(), m["command"])
        if m.get("move_id"):
            names[m["move_id"].lower()] = m["command"]
    for t in (throws or {}).get("throws", []):
        if t.get("move_id"):
            names[t["move_id"].lower()] = t["command"]
    return normalize_table({"classes": classes, "move_names": names})


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_options(character, root=ROOT, fallback=FALLBACK_PATH):
    folder = Path(root) / "characters" / character
    data = load_fallback(fallback)
    options, moves = read_json(folder / "options.json"), read_json(folder / "moves.json")
    if isinstance(options, dict) and isinstance(moves, dict):
        try:
            table = from_characters(options, moves, read_json(folder / "throws.json"), data.get(character))
        except (KeyError, TypeError, AttributeError):
            table = None
        if table and all(table["classes"][c] for c in REQUIRED):
            return table, f"{folder.as_posix()} (+ game/{Path(fallback).name} movement and throws)"
    if character in data:
        return normalize_table(data[character]), f"game/{Path(fallback).name} ({character})"
    return normalize_table(data["kazuya"]), f"game/{Path(fallback).name} (kazuya table, no data for {character})"


def move_key(command):
    return command.lower().replace(" ", "").replace("+", "").replace("/", "").replace(",", "_")


def move_name(table, move_id):
    if move_id is None:
        return None
    return table["move_names"].get(f"0x{move_id:x}")


def allowed(entry, difficulty):
    have = MOVEMENT_SETS.get(getattr(difficulty, "movement_set", "full"), 3)
    return MOVEMENT_SETS.get(entry.get("movement_set", "basic"), 0) <= have


def in_range(entry, bucket):
    return bucket in entry.get("ranges", BUCKETS)


def step_direction(notation, side):
    if notation not in ("u", "d"):
        return None
    toward_left = notation == "u" if side == 0 else notation == "d"
    return "left" if toward_left else "right"
