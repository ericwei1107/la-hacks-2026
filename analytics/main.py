import os
import subprocess
from pathlib import Path

import sentry_sdk


def git_sha():
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


VERSION = os.environ.get("SENTRY_RELEASE") or f"kumite-analytics@{git_sha()}"
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    environment=os.environ.get("SENTRY_ENVIRONMENT", "development"),
    release=VERSION,
    send_default_pii=True,
    traces_sample_rate=1.0,
    profile_session_sample_rate=1.0,
    profile_lifecycle="trace",
    enable_logs=True,
)

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from analytics.repository import DataError, FileRepository

logger = logging.getLogger(__name__)


def create_app(data_dir=None):
    app = FastAPI(title="kumite-analytics", version=VERSION)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    root = data_dir if data_dir is not None else DATA_DIR
    url = os.environ.get("DATABASE_URL")
    if url:
        from analytics.tigerdata.repository import TigerRepository
        app.state.repository = TigerRepository(root, url)
    else:
        app.state.repository = FileRepository(root)

    @app.exception_handler(DataError)
    async def unavailable(request, exc):
        logger.error("Analytics data unavailable: %s", exc)
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.get("/health")
    def health():
        return {"ok": True, "service": "analytics", "version": VERSION}

    @app.get("/stats/{session_id}")
    def stats(session_id: str):
        result = app.state.repository.stats(session_id)
        if result is None:
            raise HTTPException(404, "Unknown session")
        return result

    @app.get("/learning/{session_id}")
    def learning(session_id: str):
        result = app.state.repository.learning(session_id)
        if result is None:
            raise HTTPException(404, "Unknown session")
        return result

    @app.get("/trends/{player}/{character}")
    def trends(player: str, character: str, stat: str | None = None):
        return app.state.repository.trends(player, character, stat)

    return app


app = create_app()
