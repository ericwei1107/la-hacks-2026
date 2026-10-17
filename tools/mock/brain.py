import asyncio
import bisect
import copy
import json
import time

from fastapi import HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

import derive
from store import CONTRACTS, check, make_app

ROUND_GAP_S = 1.0


class Timeline:
    def __init__(self, session, rate):
        self.session = session
        self.rate = rate
        self.items = []
        self.round_ends = []
        tick, prev = 0, None
        for rec in session.stream():
            if rec["t"] == "round_summary":
                continue
            if prev is not None:
                if rec["round"] != prev["round"]:
                    self.round_ends.append((tick, prev["round"]))
                    tick += int(ROUND_GAP_S * rate)
                else:
                    tick += max(0, min(rec["frame"] - prev["frame"], rate))
            self.items.append((tick, rec))
            prev = rec
        if prev is not None:
            self.round_ends.append((tick, prev["round"]))
        self.total = tick + int(ROUND_GAP_S * rate) + 1
        self.ticks = [t for t, _ in self.items]

    def between(self, lo, hi):
        return self.items[bisect.bisect_right(self.ticks, lo):bisect.bisect_right(self.ticks, hi)]


class Clock:
    def __init__(self, rate):
        self.rate = rate
        self.start = time.monotonic()

    def now(self):
        return int((time.monotonic() - self.start) * self.rate)


def merge(base, patch):
    out = copy.deepcopy(base)
    for k, v in patch.items():
        out[k] = merge(out.get(k, {}), v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def create(store, rate=60, loop=True):
    app = make_app("brain")
    clock = Clock(rate)
    timelines = {}
    config = {"value": json.loads((CONTRACTS / "examples" / "config.json").read_text())}

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
        return timelines[s.id]

    @app.get("/sessions")
    def sessions():
        store.refresh()
        return [s.meta for s in store.newest()]

    @app.get("/sessions/{sid}")
    def session(sid: str):
        return session_or_404(sid).meta

    @app.get("/sessions/{sid}/recording")
    def recording(sid: str):
        return FileResponse(session_or_404(sid).path, media_type="application/x-ndjson")

    @app.get("/profiles/{player}")
    def profiles(player: str):
        found = store.profiles(player)
        if found:
            return found
        mine = [s for s in store.newest() if s.meta.get("player") == player]
        return [derive.profile(mine[0], player)] if mine else []

    @app.get("/config")
    def get_config():
        return config["value"]

    @app.post("/config")
    async def post_config(request: Request):
        patch = await request.json()
        if not isinstance(patch, dict):
            return JSONResponse({"errors": ["body must be a JSON object"]}, status_code=422)
        merged = merge(config["value"], patch)
        errors = check("config", merged)
        if errors:
            return JSONResponse({"errors": errors}, status_code=422)
        config["value"] = merged
        return merged

    async def run(ws, sid, emit):
        await ws.accept()
        tl = timeline(sid)
        if tl is None or not tl.items:
            await ws.close(code=1011)
            return
        last = clock.now()
        try:
            while True:
                await asyncio.sleep(1 / rate)
                now = clock.now()
                if not loop and now >= tl.total:
                    await ws.close()
                    return
                for lo, hi in spans(last % tl.total, now % tl.total, now - last >= tl.total):
                    await emit(ws, tl, lo, hi)
                last = now
        except (WebSocketDisconnect, RuntimeError):
            return

    def spans(a, b, full):
        if full:
            return [(0, 10 ** 12)]
        return [(a, b)] if b >= a else [(a, 10 ** 12), (-1, b)]

    async def emit_state(ws, tl, lo, hi):
        for _, rec in tl.between(lo, hi):
            await ws.send_text(json.dumps(rec))

    async def emit_coach(ws, tl, lo, hi):
        for tick, round_ in tl.round_ends:
            if lo < tick <= hi:
                summary = derive.round_summary(tl.session, round_)
                text, severity = derive.coach_text(summary)
                await ws.send_text(json.dumps(summary))
                await ws.send_text(json.dumps({"t": "coach", "session_id": tl.session.id, "round": round_, "text": text, "severity": severity}))

    @app.websocket("/ws/state")
    async def ws_state(ws: WebSocket, session: str | None = None):
        await run(ws, session, emit_state)

    @app.websocket("/ws/coach")
    async def ws_coach(ws: WebSocket, session: str | None = None):
        await run(ws, session, emit_coach)

    app.state.timeline = timeline
    app.state.clock = clock
    return app
