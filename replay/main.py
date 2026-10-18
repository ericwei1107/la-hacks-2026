import json
import asyncio
from typing import Annotated

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from jsonschema import Draft202012Validator

from replay.coach import CoachTip, OpenAIProvider, RoundCoach
from replay.config import ROOT, Settings
from replay.reports import REPORT_SCHEMA, ReportService

SCHEMA = json.loads((ROOT / "contracts/round_summary.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)
EXAMPLE = json.loads((ROOT / "contracts/examples/round_summary.json").read_text())


def create_app() -> FastAPI:
    settings = Settings.load()
    app = FastAPI(title="Kumite replay coach", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.state.settings = settings
    provider = None
    if settings.mode == "auto" and settings.api_key:
        provider = OpenAIProvider(settings.api_key, settings.model)
    app.state.coach = RoundCoach(provider)
    app.state.reports = ReportService(settings.data_dir)

    @app.get("/health")
    async def health():
        return {"ok": True, "service": "replay", "version": settings.version}

    @app.post("/coach/round", response_model=CoachTip, openapi_extra={
        "requestBody": {"required": True, "content": {
            "application/json": {"schema": SCHEMA, "example": EXAMPLE}
        }}
    })
    async def coach_round(summary: Annotated[dict, Body(examples=[EXAMPLE])]):
        errors = list(VALIDATOR.iter_errors(summary))
        if errors:
            raise HTTPException(status_code=422, detail=[
                {"loc": ["body", *error.absolute_path], "type": "contract_validation",
                 "msg": f"Round summary violates {error.validator}"}
                for error in errors
            ])
        return await app.state.coach.coach(summary)

    @app.post("/analyze/{session_id}", responses={200: {"content": {"application/json": {"schema": REPORT_SCHEMA}}}})
    async def analyze(session_id: str):
        try:
            return await app.state.reports.analyze(session_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="No extracted recording found for this session")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid session ID, recording or report data")

    @app.get("/reports/{session_id}", responses={200: {"content": {"application/json": {"schema": REPORT_SCHEMA}}}})
    async def get_report(session_id: str):
        try:
            return await asyncio.to_thread(app.state.reports.get, session_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Session has not been analyzed")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid session ID or saved report")

    return app


app = create_app()
