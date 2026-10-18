import json
import os
import time
from pathlib import Path

ORDER_WINDOW = 8
FLUSH_SECONDS = 1.0
RANK = {"round_start": 0, "state": 1}


def data_dir():
    return Path(os.environ.get("DATA_DIR", "data"))


def iso_utc(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def dumps(record):
    return json.dumps(record, separators=(",", ":"))


class Recorder:
    def __init__(self, meta, root=None):
        self.root = Path(root) if root else data_dir()
        self.meta = meta
        sid = meta["session_id"]
        self.recording_path = self.root / "recordings" / f"{sid}.jsonl"
        self.session_path = self.root / "sessions" / f"{sid}.json"
        self.recording_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        self.meta.setdefault("recording", self.recording_path.as_posix())
        self.file = open(self.recording_path, "a", encoding="utf-8", newline="\n")
        self.pending = []
        self.seq = 0
        self.lines = 0
        self.last_flush = time.monotonic()
        self.write_session()

    def _add(self, record):
        rank = RANK.get(record.get("kind", record["t"]), 2)
        self.pending.append(((record["round"], record["frame"], rank, self.seq), record))
        self.seq += 1

    def state(self, state):
        self._add(state)
        self._drain(state["round"], state["frame"] - ORDER_WINDOW)

    def events(self, events):
        for ev in events:
            self._add(ev)

    def _drain(self, round_=None, frame=None):
        self.pending.sort(key=lambda item: item[0])
        keep = []
        for key, record in self.pending:
            if round_ is None or key[0] < round_ or (key[0] == round_ and key[1] <= frame):
                self.file.write(dumps(record) + "\n")
                self.lines += 1
            else:
                keep.append((key, record))
        self.pending = keep

    def tick(self):
        now = time.monotonic()
        if now - self.last_flush >= FLUSH_SECONDS:
            self.file.flush()
            self.last_flush = now

    def write_session(self, rounds=None, ended_at=None, result=None):
        if rounds is not None:
            self.meta["rounds"] = rounds
        if ended_at is not None:
            self.meta["ended_at"] = ended_at
        if result is not None:
            self.meta["result"] = result
        tmp = self.session_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.meta, indent=2), encoding="utf-8")
        os.replace(tmp, self.session_path)

    def close(self, rounds, ended_at, result=""):
        self._drain()
        self.file.flush()
        self.file.close()
        self.write_session(rounds, ended_at, result)


def session_meta(sid, started, player, human_slot, human_character, bot_character, difficulty, mode, version, stage=None):
    meta = {
        "session_id": sid,
        "started_at": iso_utc(started),
        "ended_at": None,
        "game_version": version,
        "mode": mode,
        "player": player,
        "human_slot": human_slot,
        "human_character": human_character,
        "bot_character": bot_character,
        "difficulty": difficulty,
        "rounds": [],
        "result": "",
    }
    if stage:
        meta["stage"] = stage
    return meta


def result_text(rounds, human_slot):
    decided = [r["winner"] for r in rounds if r["winner"] is not None]
    if not decided:
        return ""
    won = sum(1 for w in decided if w == human_slot)
    lost = len(decided) - won
    return f"{'win' if won > lost else 'loss' if lost > won else 'draw'} {won}-{lost}"
