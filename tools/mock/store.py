import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"
sys.path.insert(0, str(CONTRACTS))

from validate import load_schemas, validator

SCHEMAS = load_schemas()
CHARACTERS = {"djin": "devil_jin", "kaz": "kazuya", "king": "king", "shaheen": "shaheen"}


def data_dir():
    return Path(os.environ.get("DATA_DIR", ROOT / "data"))


def check(name, obj, sub=None):
    errors = list(validator(SCHEMAS, name, sub).iter_errors(obj))
    return [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}" for e in errors]


def load_jsonl(path):
    records = []
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                break
            raise
        if isinstance(rec, dict) and "t" in rec:
            records.append(rec)
    return records


def parse_started(sid):
    try:
        return datetime.strptime(sid[:19], "%Y-%m-%dT%H-%M-%S").replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return "1970-01-01T00:00:00Z"


def fallback_meta(sid, records, path):
    states = [r for r in records if r["t"] == "state"]
    parts = sid.split("_")
    human_slot = states[0]["human_slot"] if states else 0
    chars = [p["character"] for p in states[0]["players"]] if states else ["unknown", "unknown"]
    rounds = sorted({r["round"] for r in records if "round" in r})
    return {
        "session_id": sid,
        "started_at": parse_started(sid),
        "ended_at": None,
        "mode": "practice",
        "player": parts[1] if len(parts) > 1 else "unknown",
        "human_slot": human_slot,
        "human_character": chars[human_slot],
        "bot_character": chars[1 - human_slot],
        "difficulty": 1,
        "rounds": [{"round": r, "winner": None} for r in rounds],
        "result": "",
        "recording": str(path),
    }


class Session:
    def __init__(self, path):
        self.path = Path(path)
        self.records = load_jsonl(self.path)
        self.id = next((r["session_id"] for r in self.records if r.get("session_id")), self.path.stem)
        meta_path = self.find_meta()
        self.meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path else fallback_meta(self.id, self.records, self.path)
        self.learning = self.load_learning()

    def find_meta(self):
        for candidate in (self.path.with_name(f"{self.path.stem}.session.json"), data_dir() / "sessions" / f"{self.id}.json"):
            if candidate.exists():
                return candidate
        return None

    def load_learning(self):
        inline = [r for r in self.records if r["t"] == "learning_round"]
        if inline:
            return inline
        path = data_dir() / "learning" / f"{self.id}.jsonl"
        return [r for r in load_jsonl(path) if r["t"] == "learning_round"] if path.exists() else []

    def stream(self):
        return [r for r in self.records if r["t"] in ("state", "event", "round_summary")]

    def of(self, t):
        return [r for r in self.records if r["t"] == t]


class Store:
    def __init__(self, recordings=None):
        self.explicit = [Path(p) for p in recordings] if recordings else None
        self.sessions = {}
        self.refresh()

    def paths(self):
        if self.explicit:
            return self.explicit
        found = sorted((ROOT / "data" / "samples").glob("*.jsonl"))
        found += sorted((data_dir() / "recordings").glob("*.jsonl"))
        return found

    def refresh(self):
        sessions = {}
        for path in self.paths():
            try:
                s = Session(path)
            except (OSError, json.JSONDecodeError):
                continue
            sessions[s.id] = s
        self.sessions = sessions

    def get(self, sid):
        if sid not in self.sessions:
            self.refresh()
        return self.sessions.get(sid)

    def newest(self):
        return sorted(self.sessions.values(), key=lambda s: s.meta.get("started_at", ""), reverse=True)

    def default(self):
        synthetic = [s for s in self.newest() if s.meta.get("mode") == "synthetic"]
        listed = synthetic or self.newest()
        return listed[0] if listed else None

    def profiles(self, player):
        found = []
        for path in sorted((data_dir() / "profiles").glob(f"{player}_*.json")):
            try:
                found.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return found


def git_sha():
    head = ROOT / ".git" / "HEAD"
    try:
        ref = head.read_text().strip()
        if ref.startswith("ref: "):
            return (ROOT / ".git" / ref[5:]).read_text().strip()[:7]
        return ref[:7]
    except OSError:
        return "unknown"


def make_app(service):
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title=f"kumite-mock-{service}")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    version = f"mock-{git_sha()}"

    @app.get("/health")
    def health():
        return {"ok": True, "service": service, "version": version, "mock": True}

    return app
