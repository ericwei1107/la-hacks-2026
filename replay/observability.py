import hashlib
import logging
import os
import re

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.openai import OpenAIIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.utils import BadDsn, Dsn


def scrub_urls(value):
    if isinstance(value, dict):
        return {key: scrub_urls(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub_urls(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"/(reports|analyze|learning)/[^/?#\s]+", r"/\1/{session_id}", value)
    return value


def scrub_event(event, hint):
    values = event.get("exception", {}).get("values", [])
    if any(value.get("mechanism", {}).get("type") == "openai" for value in values):
        return None
    return scrub_urls(event)


def initialize(version: str):
    if not os.getenv("SENTRY_DSN", "").strip() or sentry_sdk.is_initialized():
        return
    try:
        Dsn(os.environ["SENTRY_DSN"])
    except BadDsn:
        logging.getLogger(__name__).warning("Sentry DSN is invalid; replay telemetry is disabled")
        return
    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        release=os.getenv("SENTRY_RELEASE") or f"kumite-replay@{version}",
        environment=os.getenv("SENTRY_ENVIRONMENT") or "development",
        traces_sample_rate=1.0,
        stream_gen_ai_spans=False,
        data_collection={
            "user_info": False, "http_bodies": [],
            "gen_ai": {"inputs": False, "outputs": False},
            "http_headers": {"request": {"mode": "off"}},
            "cookies": {"mode": "off"}, "url_query_params": {"mode": "off"},
            "stack_frame_variables": False, "frame_context_lines": 0,
        },
        max_request_body_size="never",
        before_send=scrub_event,
        before_send_transaction=scrub_event,
        integrations=[FastApiIntegration(), StarletteIntegration(), OpenAIIntegration(include_prompts=False)],
    )


def agent_span(session_id: str):
    span = sentry_sdk.start_span(op="gen_ai.invoke_agent", name="round_coach")
    span.set_data("gen_ai.operation.name", "invoke_agent")
    span.set_data("gen_ai.agent.name", "round_coach")
    span.set_data("gen_ai.conversation.id", hashlib.sha256(session_id.encode()).hexdigest())
    return span


def outcome(span, value: str):
    span.set_data("coach.outcome", value)
    sentry_sdk.set_tag("coach.outcome", value)
