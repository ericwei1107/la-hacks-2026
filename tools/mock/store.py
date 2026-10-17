import json
import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"
sys.path.insert(0, str(CONTRACTS))

from validate import load_schemas, validator

SCHEMAS = load_schemas()


def data_dir():
    return Path(os.environ.get("DATA_DIR", ROOT / "data"))


def check(name, obj, sub=None):
    errors = list(validator(SCHEMAS, name, sub).iter_errors(obj))
    return [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}" for e in errors]


def load_jsonl(path):
    records = []
    raw = Path(path).read_text(encoding="utf-8")
    lines = raw.splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            if i == len(lines) - 1 and not raw.endswith("\n") and line.lstrip().startswith("{") and (exc.pos >= len(line.rstrip()) - 1 or exc.msg.startswith("Unterminated string")):
                break
            raise ValueError(f"{path}:{i + 1}: invalid JSON: {exc.msg}") from exc
        if isinstance(rec, dict) and "t" in rec:
            records.append(rec)
    return records


class Session:
    def __init__(self, path):
        self.path = Path(path)
        self.records = load_jsonl(self.path)
        self.id = next((r["session_id"] for r in self.records if r.get("session_id")), self.path.stem)
        meta_path = self.find_meta()
        if meta_path is None:
            raise ValueError(f"{self.path}: missing metadata; provide {self.path.stem}.session.json or DATA_DIR/sessions/{self.id}.json")
        self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        errors = check("session", self.meta)
        if errors or self.meta["session_id"] != self.id:
            raise ValueError(f"{meta_path}: invalid session metadata: {errors or 'session_id does not match recording'}")
        for record in self.records:
            schema = {"state": "gamestate", "event": "event", "round_summary": "round_summary"}.get(record["t"])
            if schema:
                errors = check(schema, record)
                if errors or record.get("session_id") != self.id:
                    raise ValueError(f"{self.path}: invalid {record['t']} record: {errors or 'session_id mismatch'}")
        self.learning = self.load_learning()
        for line in self.learning:
            errors = check("metrics", line, "round")
            if errors:
                raise ValueError(f"{self.path}: invalid learning data: {errors}")

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
        found = list(self.explicit or [])
        if not self.explicit:
            found.extend(sorted((ROOT / "data" / "samples").glob("*.jsonl")))
            found.extend(sorted((data_dir() / "recordings").glob("*.jsonl")))
        for meta_path in sorted((data_dir() / "sessions").glob("*.json")):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            reference = meta.get("recording")
            if reference:
                path = Path(reference)
                path = path if path.is_absolute() else ROOT / path
                if path.is_file():
                    found.append(path)
        return list(dict.fromkeys(p.resolve() for p in found))

    def refresh(self):
        self.sessions = {s.id: s for s in (Session(path) for path in self.paths())}

    def get(self, sid):
        if sid not in self.sessions:
            self.refresh()
        return self.sessions.get(sid)

    def newest(self):
        return sorted(self.sessions.values(), key=lambda s: s.meta.get("started_at", ""), reverse=True)

    def default(self):
        if self.explicit:
            selected = self.explicit[0].resolve()
            return next((s for s in self.sessions.values() if s.path.resolve() == selected), None)
        listed = self.newest()
        return listed[0] if listed else None

    def profiles(self, player):
        found = []
        for path in sorted((data_dir() / "profiles").glob("*.json")):
            obj = json.loads(path.read_text(encoding="utf-8"))
            if obj.get("player") == player:
                errors = check("profile", obj)
                if errors:
                    raise ValueError(f"{path}: invalid profile: {errors}")
                found.append(obj)
        return found


def git_sha():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def make_app(service):
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title=f"kumite-mock-{service}")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    version = git_sha()

    @app.get("/health")
    def health():
        return {"ok": True, "service": service, "version": version}

    return app
