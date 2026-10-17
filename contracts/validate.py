import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent
RECORD_TYPES = {"state": "gamestate", "event": "event", "round_summary": "round_summary", "learning_round": None}


def load_schemas():
    return {p.name.removesuffix(".schema.json"): json.loads(p.read_text()) for p in ROOT.glob("*.schema.json")}


def validator(schemas, name, sub=None):
    schema = schemas[name]
    if sub:
        schema = {**schema["$defs"][sub], "$defs": schema["$defs"]}
    return Draft202012Validator(schema, format_checker=FormatChecker())


def report(label, errors):
    for e in errors:
        path = "/".join(str(p) for p in e.absolute_path) or "(root)"
        print(f"FAIL {label}: {path}: {e.message}")
    return len(errors)


def check_examples(schemas):
    failures = 0
    for name in sorted(schemas):
        ex = ROOT / "examples" / f"{name}.json"
        if not ex.exists():
            print(f"FAIL {name}: no example")
            failures += 1
            continue
        errors = list(validator(schemas, name).iter_errors(json.loads(ex.read_text())))
        failures += report(f"examples/{name}.json", errors)
        if not errors:
            print(f"ok   examples/{name}.json")
    return failures


def check_jsonl(schemas, path):
    failures = 0
    counts = {}
    for i, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        rec = json.loads(line)
        t = rec.get("t")
        counts[t] = counts.get(t, 0) + 1
        if t == "learning_round":
            v = validator(schemas, "metrics", "round")
        elif t in RECORD_TYPES:
            v = validator(schemas, RECORD_TYPES[t])
        else:
            continue
        failures += report(f"{path}:{i}", list(v.iter_errors(rec)))
    print(f"{path}: {counts} failures={failures}")
    return failures


def main(args):
    schemas = load_schemas()
    failures = check_examples(schemas) if not args else 0
    for path in args:
        failures += check_jsonl(schemas, path)
    print("PASS" if failures == 0 else f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
