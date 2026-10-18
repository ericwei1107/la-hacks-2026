import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

from replay.config import ROOT

SCHEMAS = {
    kind: Draft202012Validator(json.loads((ROOT / f"contracts/{name}.schema.json").read_text()))
    for kind, name in {"state": "gamestate", "event": "event",
                       "round_summary": "round_summary", "plan": "gameplan"}.items()
}


@dataclass(frozen=True)
class Record:
    data: dict
    line: int


@dataclass
class Recording:
    path: Path
    session_id: str
    records: list[Record]
    counts: Counter
    warnings: list[str]


def truncated_tail(line, error):
    if line.endswith("\n") or not line.lstrip().startswith("{"):
        return False
    remaining = line[error.pos:].strip()
    if error.msg == "Invalid \\uXXXX escape":
        return bool(re.fullmatch(r"u[0-9a-fA-F]{0,3}", remaining))
    if error.msg == "Expecting value" and remaining == "-":
        return True
    if error.msg == "Expecting ',' delimiter" and remaining in {".", "e", "E", "e+", "E+", "e-", "E-"}:
        return bool(re.search(r"[:,\[]\s*-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?|\.)$", line))
    return (error.pos >= len(line.rstrip()) or error.msg.startswith("Unterminated string")
            or remaining in {"t", "tr", "tru", "f", "fa", "fal", "fals", "n", "nu", "nul"})


def read_recording(path: str | Path) -> Recording:
    path = Path(path).resolve()
    if path.suffix.lower() == ".zip":
        raise ValueError("Extract the ZIP first and pass the extracted .jsonl file")
    if path.suffix.lower() != ".jsonl":
        raise ValueError("Expected an extracted .jsonl recording")
    records, warnings = [], []
    counts = Counter()
    session_id = None
    with path.open(encoding="utf-8-sig") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as error:
                if truncated_tail(line, error):
                    warnings.append(f"Ignored truncated final JSON record at line {line_number}")
                    continue
                raise ValueError(f"Invalid JSON at line {line_number}: {error.msg}") from error
            if not isinstance(data, dict) or not isinstance(data.get("t"), str):
                raise ValueError(f"Expected a record object with t at line {line_number}")
            kind = data["t"]
            counts[kind] += 1
            if kind not in SCHEMAS and kind != "tactical":
                continue
            if kind in SCHEMAS:
                error = next(SCHEMAS[kind].iter_errors(data), None)
                if error:
                    location = "/".join(str(item) for item in error.absolute_path)
                    raise ValueError(f"Contract violation at line {line_number}, {location or 'root'}: {error.validator}")
            if not isinstance(data.get("session_id"), str) or not data["session_id"]:
                raise ValueError(f"Missing session_id at line {line_number}")
            for field in ("round",) if kind == "round_summary" else ("round", "frame"):
                value = data.get(field)
                if type(value) is not int or value < (1 if field == "round" else 0):
                    raise ValueError(f"Invalid {field} at line {line_number}")
            if session_id is not None and data["session_id"] != session_id:
                raise ValueError(f"Mixed session IDs at line {line_number}")
            session_id = data["session_id"]
            if kind == "state":
                slots = [player["slot"] for player in data["players"]]
                if sorted(slots) != [0, 1] or data["human_slot"] not in slots:
                    raise ValueError(f"Invalid player slots at line {line_number}")
            records.append(Record(data, line_number))
    if not records:
        raise ValueError("Recording contains no supported records")
    return Recording(path, session_id, records, counts, warnings)
