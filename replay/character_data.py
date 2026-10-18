import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CHARACTERS_DIR = Path(__file__).resolve().parents[1] / "characters"

CHARACTER_IDS = {"devil_jin": 12, "kazuya": 8, "king": 2, "shaheen": 20}

CHARACTER_ALIASES = {
    "devil_jin": ("devil_jin", "deviljin", "djin", "dvj"),
    "kazuya": ("kazuya", "kaz"),
    "king": ("king",),
    "shaheen": ("shaheen", "shah"),
}

_ALIAS_LOOKUP = {alias: name for name, aliases in CHARACTER_ALIASES.items() for alias in aliases}
_ID_LOOKUP = {value: name for name, value in CHARACTER_IDS.items()}

MOVE_ALIASES = {
    "kazuya": {
        "ewgf": "f,n,d,df+2 (electric)",
        "electric wind god fist": "f,n,d,df+2 (electric)",
        "wgf": "f,n,d,df+2",
        "wind god fist": "f,n,d,df+2",
        "hellsweep": "f,n,d,DF+4",
    },
    "devil_jin": {
        "ewgf": "f,n,d,df+2 (electric)",
        "electric wind god fist": "f,n,d,df+2 (electric)",
        "wgf": "f,n,d,df+2",
        "wind god fist": "f,n,d,df+2",
    },
}

_DIRECTION_PAIRS = (("d/f", "df"), ("d/b", "db"), ("u/f", "uf"), ("u/b", "ub"))


class CharacterDataError(ValueError):
    pass


def normalize_character(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return _ID_LOOKUP.get(value)
    if not isinstance(value, str):
        return None
    text = re.sub(r"[\s\-]+", "_", value.strip().lower())
    return _ALIAS_LOOKUP.get(text) or _ALIAS_LOOKUP.get(text.replace("_", ""))


def normalize_move_id(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if not isinstance(value, str):
        return None
    text = value.strip()
    hexadecimal = re.fullmatch(r"0[xX]([0-9a-fA-F]+)", text)
    if hexadecimal:
        return int(hexadecimal.group(1), 16)
    if re.fullmatch(r"[0-9]+", text):
        return int(text)
    return None


def format_move_id(value):
    number = normalize_move_id(value)
    return None if number is None else f"0x{number:X}"


def normalize_command(text):
    if not isinstance(text, str):
        return ""
    command = re.sub(r"\s+(?=\()", " ", text.strip())
    command = re.sub(r"\s*,\s*", ",", command)
    command = re.sub(r"\s*\+\s*", "+", command)
    for source, target in _DIRECTION_PAIRS:
        command = re.sub(source, target, command, flags=re.IGNORECASE)
    return re.sub(r"^ws\+", "ws", command, flags=re.IGNORECASE)


def _name_key(text):
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


@dataclass(frozen=True)
class Resolution:
    status: str
    move: dict | None
    candidates: tuple
    reason: str

    @property
    def found(self):
        return self.status == "unique"


def _unknown(reason):
    return Resolution("unknown", None, (), reason)


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _parse_tables(text):
    sections, tables, current, rows = {}, {}, None, []
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
            continue
        if current is not None:
            sections[current].append(line)
    for title, lines in sections.items():
        header, rows = None, []
        for line in lines:
            if not line.startswith("|"):
                continue
            cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
            if header is None:
                header = cells
            elif all(re.fullmatch(r":?-+:?", cell) for cell in cells):
                continue
            else:
                rows.append(dict(zip(header, cells)))
        if rows:
            tables[title] = rows
    return {title: "\n".join(lines).strip() for title, lines in sections.items()}, tables


@dataclass(frozen=True)
class MatchupNotes:
    human: str
    opponent: str
    path: Path
    text: str
    sections: dict
    tables: dict

    @property
    def expectations(self):
        body = self.sections.get("What to expect", "")
        return [line[2:].strip() for line in body.splitlines() if line.startswith("- ")]

    @property
    def punishable(self):
        return self.tables.get("Punishable on block", [])

    def punish_row(self, opponent_command):
        wanted = normalize_command(opponent_command)
        for row in self.punishable:
            if normalize_command(row.get("Move", "")) == wanted:
                return row
        return None


class CharacterData:
    def __init__(self, name, directory):
        self.name = name
        self.character_id = CHARACTER_IDS[name]
        self.directory = Path(directory)
        moves_path = self.directory / "moves.json"
        if not moves_path.is_file():
            raise CharacterDataError(f"Missing moves.json for {name}")
        payload = _read_json(moves_path)
        self.moves = payload["moves"]
        self.throws = self._optional("throws.json", {"throws": []})["throws"]
        self.punishers = self._optional("punishers.json", {"tiers": {}, "whiff": {}})
        self.options = self._optional("options.json", {})
        self.combos = self._optional("combos.json", {})
        gameplan = self.directory / "gameplan.md"
        self.gameplan = gameplan.read_text(encoding="utf-8") if gameplan.is_file() else ""
        self.by_command = {move["command"]: move for move in self.moves}
        self.throw_by_command = {throw["command"]: throw for throw in self.throws}
        self._exact = {normalize_command(command): command for command in self.by_command}
        self._folded = {}
        for command in self.by_command:
            self._folded.setdefault(normalize_command(command).lower(), set()).add(command)
        self._names = {}
        for move in self.moves:
            if move.get("name"):
                self._names.setdefault(_name_key(move["name"]), set()).add(move["command"])
        self._aliases = {
            _name_key(alias): target
            for alias, target in MOVE_ALIASES.get(name, {}).items()
            if target in self.by_command
        }
        self._ids = {}
        for move in self.moves:
            for raw in list(move.get("move_ids") or []) + [move.get("move_id")]:
                number = normalize_move_id(raw)
                if number is not None:
                    self._ids.setdefault(number, set()).add(move["command"])
        for throw in self.throws:
            number = normalize_move_id(throw.get("move_id"))
            if number is not None and throw["command"] in self.by_command:
                self._ids.setdefault(number, set()).add(throw["command"])
        self._matchups = {}

    def _optional(self, filename, default):
        path = self.directory / filename
        return _read_json(path) if path.is_file() else default

    def resolve_move_id(self, value):
        number = normalize_move_id(value)
        if number is None:
            return _unknown(f"{value!r} is not a recognizable move ID")
        commands = sorted(self._ids.get(number, ()))
        if not commands:
            return _unknown(f"{format_move_id(number)} is not a verified {self.name} move ID")
        if len(commands) > 1:
            return Resolution("ambiguous", None, tuple(commands),
                              f"{format_move_id(number)} is shared by several {self.name} moves")
        return Resolution("unique", self.by_command[commands[0]], tuple(commands), "")

    def resolve_move(self, query):
        if isinstance(query, (int, bool)) or (isinstance(query, str) and re.fullmatch(r"\s*0[xX][0-9a-fA-F]+\s*", query)):
            return self.resolve_move_id(query)
        if not isinstance(query, str) or not query.strip():
            return _unknown("Empty move query")
        text = query.strip()
        command = normalize_command(text)
        if command in self._exact:
            move = self.by_command[self._exact[command]]
            return Resolution("unique", move, (move["command"],), "")
        alias = self._aliases.get(_name_key(text))
        if alias:
            return Resolution("unique", self.by_command[alias], (alias,), "")
        folded = self._folded.get(command.lower())
        if folded:
            return self._from_candidates(folded, f"{query!r} matches several {self.name} commands")
        named = self._names.get(_name_key(text))
        if named:
            return self._from_candidates(named, f"{query!r} names several {self.name} moves")
        return _unknown(f"{query!r} is not a known {self.name} move")

    def _from_candidates(self, commands, reason):
        ordered = tuple(sorted(commands))
        if len(ordered) == 1:
            return Resolution("unique", self.by_command[ordered[0]], ordered, "")
        return Resolution("ambiguous", None, ordered, reason)

    def label(self, move):
        return move.get("name") or move["command"]

    def throw_break(self, command):
        throw = self.throw_by_command.get(command)
        return throw.get("break") if throw else None

    def punish_tier(self, advantage, crouching=False):
        if not isinstance(advantage, int) or isinstance(advantage, bool) or advantage > -10:
            return []
        tier = str(min(20, -advantage))
        entry = self.punishers.get("tiers", {}).get(tier)
        if not entry:
            return []
        return entry["crouching" if crouching else "standing"]

    def matchup(self, opponent):
        key = normalize_character(opponent)
        if key is None:
            return None
        if key not in self._matchups:
            path = self.directory / "matchups" / f"{key}.md"
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                sections, tables = _parse_tables(text)
                self._matchups[key] = MatchupNotes(self.name, key, path, text, sections, tables)
            else:
                self._matchups[key] = None
        return self._matchups[key]


@lru_cache(maxsize=None)
def _load(name, directory):
    return CharacterData(name, directory)


def load_character(character, characters_dir=None):
    name = normalize_character(character)
    if name is None:
        raise CharacterDataError(f"Unknown character {character!r}")
    root = Path(characters_dir) if characters_dir else CHARACTERS_DIR
    return _load(name, str(root / name))


def load_matchup(human, opponent, characters_dir=None):
    return load_character(human, characters_dir).matchup(opponent)


def resolve_move(character, query, characters_dir=None):
    return load_character(character, characters_dir).resolve_move(query)
