import argparse
import asyncio
import copy
import json
import os
import re
import subprocess
import threading
from collections import deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from jsonschema import Draft202012Validator

from game.recorder import data_dir

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
SERVICE = "brain"
HOST = "127.0.0.1"
PORT = 8765
CHANNELS = {"state": "state", "gamestate": "state", "event": "state", "round_summary": "coach", "coach": "coach"}
STATE_BACKLOG = 120
MAX_BACKLOG = 5000
SEND_TIMEOUT = 2.0
CHUNK = 1 << 16
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
DEFAULT_CONFIG = {"difficulty": 3, "knobs": {}, "bot_character": "kazuya", "player": "sahil", "demo_mode": False, "voice": True}
CONFIG_VALIDATOR = Draft202012Validator(json.loads((CONTRACTS / "config.schema.json").read_text(encoding="utf-8")))


def git_sha():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


class Subscriber:
    def __init__(self, loop, state_backlog, max_backlog):
        self.loop = loop
        self.state_backlog = state_backlog
        self.max_backlog = max_backlog
        self.queue = deque()
        self.wake = asyncio.Event()
        self.pending = False
        self.overflow = False
        self.dropped = 0

    def push(self, text, droppable):
        if self.overflow:
            return
        if droppable and len(self.queue) >= self.state_backlog:
            self.dropped += 1
            return
        if len(self.queue) >= self.max_backlog:
            self.overflow = True
            self.queue.clear()
        else:
            self.queue.append(text)
        if not self.pending:
            self.pending = True
            try:
                self.loop.call_soon_threadsafe(self.wake.set)
            except RuntimeError:
                pass

    async def next_batch(self):
        await self.wake.wait()
        self.wake.clear()
        self.pending = False
        batch = []
        while self.queue:
            batch.append(self.queue.popleft())
        return batch


class Hub:
    def __init__(self, state_backlog=STATE_BACKLOG, max_backlog=MAX_BACKLOG):
        self.state_backlog = state_backlog
        self.max_backlog = max_backlog
        self.lock = threading.Lock()
        self.subscribers = {"state": (), "coach": ()}

    def subscribe(self, channel):
        sub = Subscriber(asyncio.get_running_loop(), self.state_backlog, self.max_backlog)
        with self.lock:
            self.subscribers[channel] = self.subscribers[channel] + (sub,)
        return sub

    def unsubscribe(self, channel, sub):
        with self.lock:
            self.subscribers[channel] = tuple(s for s in self.subscribers[channel] if s is not sub)

    def publish(self, record):
        try:
            channel = CHANNELS.get(record.get("t"))
            if channel is None:
                return
            subs = self.subscribers[channel]
            if not subs:
                return
            text = json.dumps(record, separators=(",", ":"))
            droppable = channel == "state" and record.get("t") != "event"
            for sub in subs:
                sub.push(text, droppable)
        except Exception:
            return


HUB = Hub()


def publish(record):
    HUB.publish(record)


def merge(base, patch):
    out = copy.deepcopy(base)
    for key, value in patch.items():
        if value is None:
            out.pop(key, None)
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def config_errors(config):
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message}" for e in CONFIG_VALIDATOR.iter_errors(config)]


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def create_app(root=None, hub=None):
    hub = hub or HUB
    version = git_sha()
    config_lock = threading.Lock()
    app = FastAPI(title="kumite-brain")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def base():
        return Path(root) if root else data_dir()

    def checked_id(value):
        if not SAFE_ID.match(value) or ".." in value:
            raise HTTPException(404, f"unknown session {value}")
        return value

    def load_config():
        stored = read_json(base() / "config.json")
        if isinstance(stored, dict):
            merged = merge(DEFAULT_CONFIG, stored)
            if not config_errors(merged):
                return merged
        return copy.deepcopy(DEFAULT_CONFIG)

    @app.get("/health")
    def health():
        return {"ok": True, "service": SERVICE, "version": version}

    @app.get("/sessions")
    def sessions():
        found = []
        for path in (base() / "sessions").glob("*.json"):
            meta = read_json(path)
            if isinstance(meta, dict) and isinstance(meta.get("session_id"), str):
                found.append(meta)
        found.sort(key=lambda m: (str(m.get("started_at", "")), m["session_id"]), reverse=True)
        return found

    @app.get("/sessions/{sid}")
    def session(sid: str):
        meta = read_json(base() / "sessions" / f"{checked_id(sid)}.json")
        if not isinstance(meta, dict):
            raise HTTPException(404, f"unknown session {sid}")
        return meta

    @app.get("/sessions/{sid}/recording")
    def recording(sid: str):
        path = base() / "recordings" / f"{checked_id(sid)}.jsonl"
        try:
            handle = open(path, "rb")
        except OSError:
            raise HTTPException(404, f"no recording for {sid}")
        size = os.fstat(handle.fileno()).st_size

        def body():
            with handle:
                left = size
                while left > 0:
                    chunk = handle.read(min(CHUNK, left))
                    if not chunk:
                        return
                    left -= len(chunk)
                    yield chunk

        return StreamingResponse(body(), media_type="application/x-ndjson", headers={"Content-Length": str(size)})

    @app.get("/profiles/{player}")
    def profiles(player: str):
        found = []
        for path in sorted((base() / "profiles").glob("*.json")):
            profile = read_json(path)
            if isinstance(profile, dict) and profile.get("player") == player:
                found.append(profile)
        return found

    @app.get("/config")
    def get_config():
        return load_config()

    @app.post("/config")
    async def post_config(request: Request):
        try:
            patch = json.loads(await request.body())
        except ValueError:
            return JSONResponse({"errors": ["body must be valid JSON"]}, status_code=422)
        if not isinstance(patch, dict):
            return JSONResponse({"errors": ["body must be a JSON object"]}, status_code=422)
        with config_lock:
            merged = merge(load_config(), patch)
            errors = config_errors(merged)
            if errors:
                return JSONResponse({"errors": errors}, status_code=422)
            write_json(base() / "config.json", merged)
        return merged

    async def stream(ws, channel):
        sub = hub.subscribe(channel)
        try:
            await ws.accept()

            async def send():
                while True:
                    batch = await sub.next_batch()
                    if sub.overflow:
                        return 1013
                    for text in batch:
                        await asyncio.wait_for(ws.send_text(text), timeout=SEND_TIMEOUT)

            async def receive():
                while True:
                    message = await ws.receive()
                    if message["type"] == "websocket.disconnect":
                        return None

            sender = asyncio.create_task(send())
            receiver = asyncio.create_task(receive())
            done, rest = await asyncio.wait((sender, receiver), return_when=asyncio.FIRST_COMPLETED)
            for task in rest:
                task.cancel()
            await asyncio.gather(*rest, return_exceptions=True)
            if sender in done:
                code = 1013 if sender.exception() is not None else sender.result()
                try:
                    await ws.close(code=code)
                except Exception:
                    pass
        finally:
            hub.unsubscribe(channel, sub)

    @app.websocket("/ws/state")
    async def ws_state(ws: WebSocket):
        await stream(ws, "state")

    @app.websocket("/ws/coach")
    async def ws_coach(ws: WebSocket):
        await stream(ws, "coach")

    app.state.hub = hub
    return app


def start(host=HOST, port=PORT, root=None):
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(create_app(root), host=host, port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, name="brain-api", daemon=True)
    thread.start()
    return server, thread


def main(argv=None):
    import uvicorn

    parser = argparse.ArgumentParser(description="Kumite brain API")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args(argv)
    print(f"brain API on http://{args.host}:{args.port} DATA_DIR={data_dir().resolve()}")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
