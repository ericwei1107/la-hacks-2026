import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

from store import ROOT

DROPPED = ("ended_at", "result", "recording")
FLUSH_SECONDS = 1.0


def line(record):
    return (json.dumps(record, separators=(",", ":")) + "\n").encode("utf-8")


class LiveWriter:
    def __init__(self, session, directory, learning_delay=3.0, flush_seconds=FLUSH_SECONDS, clock=time.monotonic):
        if learning_delay < 0:
            raise ValueError("learning delay must not be negative")
        self.session_id = session.id
        self.root = Path(directory).resolve()
        if self.root.is_relative_to((ROOT / "data" / "samples").resolve()):
            raise ValueError("choose a live directory outside data/samples")
        self.recording = self.root / "recordings" / f"{session.id}.jsonl"
        self.learning_path = self.root / "learning" / f"{session.id}.jsonl"
        sources = {session.path.resolve()}
        if any(path.resolve() in sources for path in (self.recording, self.learning_path)):
            raise ValueError("the live directory must not contain the streamed source recording")
        self.delay = learning_delay
        self.learning = {record["round"]: record for record in session.learning}
        self.written = set()
        self.flush_seconds = flush_seconds
        self.clock = clock
        self.pending = []
        self.flushed = clock()
        for folder in ("sessions", "recordings", "learning"):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        meta = {key: value for key, value in session.meta.items() if key not in DROPPED}
        meta["rounds"] = []
        self.replace(self.root / "sessions" / f"{session.id}.json", (json.dumps(meta, indent=2) + "\n").encode("utf-8"))
        self.recording.write_bytes(b"")
        self.learning_path.write_bytes(b"")

    def replace(self, path, content):
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            stream.write(content)
        os.replace(stream.name, path)

    def append(self, path, record):
        with path.open("ab") as stream:
            stream.write(line(record))

    def flush(self):
        if self.pending:
            with self.recording.open("ab") as stream:
                stream.write(b"".join(self.pending))
            self.pending = []
        self.flushed = self.clock()

    def record(self, channel, record):
        if not isinstance(record, dict):
            return
        if channel == "state" and record.get("t") in ("state", "event"):
            self.pending.append(line(record))
            if self.clock() - self.flushed >= self.flush_seconds:
                self.flush()
        elif channel == "coach" and record.get("t") == "round_summary" and record["round"] not in self.written:
            self.written.add(record["round"])
            self.pending.append(line(record))
            self.flush()
            if record["round"] in self.learning:
                if self.delay:
                    asyncio.get_running_loop().call_later(self.delay, self.learn, record["round"])
                else:
                    self.learn(record["round"])

    def learn(self, round_):
        self.append(self.learning_path, self.learning[round_])
