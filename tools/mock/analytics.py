from fastapi import HTTPException

import derive
from store import make_app


def create(store):
    app = make_app("analytics")

    def session_or_404(sid):
        s = store.get(sid)
        if s is None:
            raise HTTPException(404, f"unknown session {sid}")
        return s

    @app.get("/stats/{sid}")
    def stats(sid: str):
        return derive.stats(session_or_404(sid))

    @app.get("/learning/{sid}")
    def learning(sid: str):
        return derive.learning(session_or_404(sid))

    @app.get("/trends/{player}/{character}")
    def trends(player: str, character: str, stat: str | None = None):
        store.refresh()
        series = []
        for s in sorted(store.sessions.values(), key=lambda s: s.meta.get("started_at", "")):
            if s.meta.get("player") != player or s.meta.get("human_character") != character:
                continue
            values = {k: v for k, v in derive.stats(s)["totals"].items() if not isinstance(v, dict)}
            if stat:
                values = {stat: values.get(stat)}
            series.append({"session_id": s.id, "started_at": s.meta.get("started_at"), "values": values})
        return {"player": player, "character": character, "series": series}

    return app
