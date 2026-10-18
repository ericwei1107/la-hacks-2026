import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator

from replay.config import ROOT
from replay.reader import truncated_tail

ROUND_SCHEMA = json.loads((ROOT / "contracts/metrics.schema.json").read_text())["$defs"]["round"]
ROUND_VALIDATOR = Draft202012Validator(ROUND_SCHEMA)


def finite_numbers(value):
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(finite_numbers(item) for item in value.values())
    if isinstance(value, list):
        return all(finite_numbers(item) for item in value)
    return True


def latest_mastery(path: Path, session_id: str, last_round: int):
    snapshots, warnings = [], []
    try:
        with path.open(encoding="utf-8-sig") as source:
            for line_number, line in enumerate(source, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as error:
                    if truncated_tail(line, error):
                        warnings.append(f"Ignored truncated final learning record at line {line_number}")
                        continue
                    raise ValueError(f"Invalid learning JSON at line {line_number}") from error
                if not isinstance(row, dict):
                    raise ValueError(f"Invalid learning record at line {line_number}")
                if row.get("t") != "learning_round":
                    continue
                if row.get("session_id") != session_id:
                    raise ValueError(f"Learning session mismatch at line {line_number}")
                if not ROUND_VALIDATOR.is_valid(row) or not finite_numbers(row):
                    warnings.append(f"Ignored invalid learning snapshot at line {line_number}")
                    continue
                if row["round"] > last_round:
                    warnings.append(f"Ignored learning round {row['round']} beyond the analyzed recording")
                    continue
                snapshots.append((row["round"], line_number, row))
    except FileNotFoundError:
        return {}, ["Learning file is missing; mastery is omitted"]
    except (OSError, ValueError) as error:
        detail = str(error) if isinstance(error, ValueError) else "Learning file could not be read"
        return {}, [*warnings, f"{detail}; mastery is omitted"]
    if not snapshots:
        return {}, [*warnings, "No valid learning snapshot is available; mastery is omitted"]
    round_number, line_number, latest = max(snapshots, key=lambda item: item[:2])
    values = {situation: {"mastery": habit["mastery"], "round": round_number, "line": line_number}
              for situation, habit in latest["habits"].items() if "mastery" in habit}
    if round_number < last_round:
        warnings.append(f"Latest learning snapshot is from round {round_number}; later-round mastery is unavailable")
    return values, warnings
