import json
import asyncio
import os
from typing import Annotated

from fastapi import Body, FastAPI, HTTPException, Response
import sentry_sdk
from fastapi.middleware.cors import CORSMiddleware
from jsonschema import Draft202012Validator

from replay.coach import CoachTip, OpenAIProvider, RoundCoach
from replay.config import ROOT, Settings
from replay.learning import finite_numbers
from replay.reports import REPORT_SCHEMA, ReportService
from replay.chat import ChatReply, ChatRequest, ChatService, OpenAIChatProvider
from replay.observability import initialize

SCHEMA = json.loads((ROOT / "contracts/round_summary.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)
EXAMPLE = json.loads((ROOT / "contracts/examples/round_summary.json").read_text())


def create_app() -> FastAPI:
    settings = Settings.load()
    initialize(settings.version)
    app = FastAPI(title="Kumite replay coach", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.state.settings = settings
    provider = chat_provider = None
    if settings.llm == "anthropic":
        from replay.claude_provider import ClaudeChatProvider, ClaudeRoundProvider

        provider = ClaudeRoundProvider(settings.anthropic_round_model)
        chat_provider = ClaudeChatProvider(settings.anthropic_chat_model)
        workspace = os.getenv("ANTHROPIC_WORKSPACE_ID", "").strip()
        print(f"coach model: Claude ({settings.anthropic_round_model} between rounds, {settings.anthropic_chat_model} in chat)"
              + (f", workspace {workspace}" if workspace else ", no ANTHROPIC_WORKSPACE_ID (needed for an organization key)"), flush=True)
    elif settings.llm == "openai":
        provider = OpenAIProvider(settings.api_key, settings.model)
        chat_provider = OpenAIChatProvider(settings.api_key, os.getenv("OPENAI_CHAT_MODEL", settings.model))
        print(f"coach model: OpenAI ({settings.model})", flush=True)
    else:
        print("coach model: none (local tips); set ANTHROPIC_API_KEY or OPENAI_API_KEY in the root .env to enable one", flush=True)
    app.state.coach = RoundCoach(provider, data_dir=settings.data_dir)
    app.state.reports = ReportService(settings.data_dir)
    app.state.chat = ChatService(app.state.reports, chat_provider,
                                 os.getenv("KUMITE_ANALYTICS_URL", "http://127.0.0.1:8767"))

    @app.get("/health")
    async def health():
        return {"ok": True, "service": "replay", "version": settings.version}

    @app.post("/coach/round", response_model=CoachTip, openapi_extra={
        "requestBody": {"required": True, "content": {
            "application/json": {"schema": SCHEMA, "example": EXAMPLE}
        }}
    })
    async def coach_round(summary: Annotated[dict, Body(examples=[EXAMPLE])], response: Response):
        if not finite_numbers(summary):
            raise HTTPException(status_code=422, detail="Round summary numbers must be finite")
        errors = list(VALIDATOR.iter_errors(summary))
        if errors:
            raise HTTPException(status_code=422, detail=[
                {"loc": ["body", *error.absolute_path], "type": "contract_validation",
                 "msg": f"Round summary violates {error.validator}"}
                for error in errors
            ])
        tip = await app.state.coach.coach(summary)
        if sentry_sdk.is_initialized():
            span = sentry_sdk.get_current_span()
            if span is not None:
                response.headers["X-Sentry-Trace-Id"] = span.trace_id
        return tip

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

    @app.post("/coach/chat", response_model=ChatReply)
    async def coach_chat(request: ChatRequest):
        try:
            return await app.state.chat.reply(request)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="No extracted recording found for this session")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid session recording or evidence")

    return app


app = create_app()
