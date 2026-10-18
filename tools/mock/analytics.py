from fastapi import HTTPException

import derive
from store import check, make_app


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
        body = derive.learning(session_or_404(sid))
        errors = check("metrics", body)
        if errors:
            raise HTTPException(500, {"errors": errors})
        return body

    @app.get("/trends/{player}/{character}")
    def trends(player: str, character: str, stat: str | None = None):
        store.refresh()
        series = []
        for s in sorted(store.sessions.values(), key=lambda s: s.meta.get("started_at", "")):
            if s.meta.get("player") != player or s.meta.get("human_character") != character:
                continue
            values = {k: v for k, v in derive.stats(s)["totals"].items() if v is None or isinstance(v, (int, float))}
            if stat:
                values = {stat: values[stat]} if stat in values else {}
            series.append({"session_id": s.id, "started_at": s.meta.get("started_at"), "values": values})
        return {"player": player, "character": character, "series": series}

    return app
