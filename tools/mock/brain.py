import asyncio
import copy
import json
import time

from anyio import CancelScope
from fastapi import HTTPException, Request, WebSocket
from contextlib import asynccontextmanager
from fastapi.responses import FileResponse, JSONResponse, Response

import derive
from store import CONTRACTS, check, make_app


class Timeline:
    def __init__(self, session, rate=60):
        if rate <= 0:
            raise ValueError("rate must be positive")
        self.session = session
        self.rate = rate
        self.items = []
        tick = 0
        for round_ in derive.rounds(session):
            records = [r for r in session.stream() if r["round"] == round_ and r["t"] != "round_summary"]
            first = records[0]["frame"] if records else 0
            last = first
            for rec in records:
                last = max(last, rec["frame"])
                self.items.append((tick + last - first, "state", rec))
            summary = derive.round_summary(session, round_)
            errors = check("round_summary", summary)
            if errors:
                raise ValueError(f"invalid round summary: {errors}")
            boundary = tick + max(last, summary.get("frame", last)) - first
            text, severity = derive.coach_text(summary)
            self.items.append((boundary, "coach", summary))
            self.items.append((boundary, "coach", {"t": "coach", "session_id": session.id, "round": round_, "text": text, "severity": severity}))
            tick = boundary + 1
        self.total = max(tick, 1)

    async def play(self, publish, loop=True, monotonic=time.monotonic, sleep=asyncio.sleep):
        start = monotonic()
        cycle = 0
        while True:
            for tick, channel, record in self.items:
                delay = start + (cycle * self.total + tick) / self.rate - monotonic()
                if delay > 0:
                    await sleep(delay)
                publish(channel, record)
            delay = start + ((cycle + 1) * self.total) / self.rate - monotonic()
            if delay > 0:
                await sleep(delay)
            if not loop:
                return
            cycle += 1


DROP = {"t": "drop"}


class Broadcast:
    def __init__(self, capacity=256):
        self.capacity = capacity
        self.subscribers = {"state": set(), "coach": set()}

    def subscribe(self, channel):
        queue = asyncio.Queue(self.capacity)
        self.subscribers[channel].add(queue)
        return queue

    def publish(self, channel, record):
        for queue in tuple(self.subscribers[channel]):
            if queue.full():
                if record is not None and record.get("t") == "state":
                    continue
                self.subscribers[channel].discard(queue)
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
            else:
                queue.put_nowait(record)

    def close(self):
        for channel in self.subscribers:
            self.publish(channel, None)


def merge(base, patch):
    out = copy.deepcopy(base)
    for k, v in patch.items():
        out[k] = merge(out.get(k, {}), v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def create(store, rate=60, loop=True, observer=None, duplicate_summaries=False, drop_after_coach=False):
    app = make_app("brain")
    timelines = {}
    broadcasts = {}
    tasks = {}
    running = False
    config = {"value": json.loads((CONTRACTS / "examples" / "config.json").read_text())}

    default = store.default()
    if default:
        config["value"].update(player=default.meta["player"], bot_character=default.meta["bot_character"])

    def session_or_404(sid):
        s = store.get(sid)
        if s is None:
            raise HTTPException(404, f"unknown session {sid}")
        return s

    def timeline(sid):
        s = store.get(sid) if sid else store.default()
        if s is None:
            return None
        if s.id not in timelines:
            timelines[s.id] = Timeline(s, rate)
            broadcasts[s.id] = Broadcast()
        if running and s.id not in tasks:
            publish = broadcasts[s.id].publish

            def emit(channel, record):
                if observer is not None and observer.session_id == s.id:
                    observer.record(channel, record)
                publish(channel, record)
                if channel == "coach" and record.get("t") == "round_summary" and duplicate_summaries:
                    publish(channel, record)
                if channel == "coach" and record.get("t") == "coach" and drop_after_coach:
                    publish("state", DROP)
                    publish("coach", DROP)

            async def play():
                try:
                    await timelines[s.id].play(emit, loop=loop)
                finally:
                    broadcasts[s.id].close()
            tasks[s.id] = asyncio.create_task(play())
        return timelines[s.id]

    @asynccontextmanager
    async def lifespan(app):
        nonlocal running
        running = True
        timeline(None)
        try:
            yield
        finally:
            running = False
            for task in tasks.values():
                task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)

    app.router.lifespan_context = lifespan

    @app.get("/sessions")
    def sessions():
        store.refresh()
        return [s.meta for s in store.newest()]

    @app.get("/sessions/{sid}")
    def session(sid: str):
        return session_or_404(sid).meta

    @app.get("/sessions/{sid}/recording")
    def recording(sid: str):
        session = session_or_404(sid)
        if session.recording_bytes is not None:
            return Response(session.recording_bytes, media_type="application/x-ndjson")
        return FileResponse(session.path, media_type="application/x-ndjson")

    @app.get("/profiles/{player}")
    def profiles(player: str):
        return store.profiles(player)

    @app.get("/config")
    def get_config():
        return config["value"]

    @app.post("/config")
    async def post_config(request: Request):
        try:
            patch = await request.json()
        except ValueError:
            raise HTTPException(422, "body must be valid JSON")
        if not isinstance(patch, dict):
            return JSONResponse({"errors": ["body must be a JSON object"]}, status_code=422)
        merged = merge(config["value"], patch)
        errors = check("config", merged)
        if errors:
            return JSONResponse({"errors": errors}, status_code=422)
        config["value"] = merged
        return merged

    async def run(ws, sid, channel):
        await ws.accept()
        tl = timeline(sid)
        if tl is None or not tl.items:
            await ws.close(code=1008)
            return
        if tasks.get(tl.session.id) is not None and tasks[tl.session.id].done():
            await ws.close(code=1000)
            return
        broadcaster = broadcasts[tl.session.id]
        queue = broadcaster.subscribe(channel)

        async def send():
            while True:
                record = await queue.get()
                if record is None:
                    await ws.close(code=1013 if loop else 1000)
                    return
                if record is DROP:
                    await ws.close(code=1013)
                    return
                await asyncio.wait_for(ws.send_text(json.dumps(record)), timeout=2)

        async def receive():
            while True:
                await ws.receive_text()

        sender = asyncio.create_task(send())
        receiver = asyncio.create_task(receive())
        try:
            done, _ = await asyncio.wait((sender, receiver), return_when=asyncio.FIRST_COMPLETED)
            if sender in done and isinstance(sender.exception(), asyncio.TimeoutError):
                await ws.close(code=1013)
        except asyncio.CancelledError:
            pass
        finally:
            broadcaster.subscribers[channel].discard(queue)
            sender.cancel()
            receiver.cancel()
            with CancelScope(shield=True):
                await asyncio.gather(sender, receiver, return_exceptions=True)

    @app.websocket("/ws/state")
    async def ws_state(ws: WebSocket, session: str | None = None):
        await run(ws, session, "state")

    @app.websocket("/ws/coach")
    async def ws_coach(ws: WebSocket, session: str | None = None):
        await run(ws, session, "coach")

    app.state.timeline = timeline
    app.state.broadcasts = broadcasts
    return app
