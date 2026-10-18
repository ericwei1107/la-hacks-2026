import json
from typing import Annotated

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from jsonschema import Draft202012Validator

from replay.coach import CoachTip, OpenAIProvider, RoundCoach
from replay.config import ROOT, Settings

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

    return app


app = create_app()
