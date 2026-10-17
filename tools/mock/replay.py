import json

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

import derive
from store import check, data_dir, make_app


def create(store):
    app = make_app("replay")

    def reports_dir():
        d = data_dir() / "reports"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @app.post("/coach/round")
    async def coach_round(request: Request):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(422, "body must be valid JSON")
        errors = check("round_summary", body)
        if errors:
            return JSONResponse({"errors": errors}, status_code=422)
        text, severity = derive.coach_text(body)
        return {"text": text, "severity": severity}

    @app.post("/analyze/{sid}")
    def analyze(sid: str):
        s = store.get(sid)
        if s is None:
            raise HTTPException(404, f"unknown session {sid}")
        rep = derive.report(s)
        errors = check("report", rep)
        if errors:
            raise HTTPException(500, {"errors": errors})
        (reports_dir() / f"{sid}.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
        return rep

    @app.get("/reports/{sid}")
    def get_report(sid: str):
        if store.get(sid) is None:
            raise HTTPException(404, f"unknown session {sid}")
        path = data_dir() / "reports" / f"{sid}.json"
        if not path.exists():
            raise HTTPException(404, f"session {sid} not analyzed")
        report = json.loads(path.read_text(encoding="utf-8"))
        errors = check("report", report)
        if errors or report["session_id"] != sid:
            raise HTTPException(500, "saved report does not match the session contract")
        return report

    @app.post("/coach/chat")
    async def coach_chat(request: Request):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(422, "body must be valid JSON")
        sid = body.get("session_id") if isinstance(body, dict) else None
        s = store.get(sid) if sid else None
        if s is None:
            return {"text": "Mock coach: I don't have that session loaded. Ask about one from GET /sessions.", "citations": []}
        summaries = [derive.round_summary(s, r) for r in derive.rounds(s)]
        moments = sorted((dict(m, round=x["round"]) for x in summaries for m in x["biggest_moments"]), key=lambda m: m.get("damage", 0), reverse=True)
        if not moments:
            return {"text": "Mock coach: nothing landed on you in that session, so there's nothing to fix yet.", "citations": []}
        top = moments[0]
        text = f"Mock coach: your most expensive moment was a {top['kind']} in round {top['round']} for {top.get('damage', 0)} damage. Block low after my df+1 and look for the punish."
        return {"text": text, "citations": [{"frame": top["frame"], "round": top["round"]}]}

    return app
