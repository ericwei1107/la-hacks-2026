import asyncio
import copy
import json
from pathlib import Path

import httpx
import pytest
import sentry_sdk
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from sentry_sdk.transport import Transport

EXAMPLE = json.loads((Path(__file__).resolve().parents[2] / "contracts/examples/round_summary.json").read_text())
SELECTED = "You have a low-defense pattern across 7 observations. Practice crouch-blocking predictable lows."


class Capture(Transport):
    def __init__(self):
        super().__init__()
        self.events = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.headers.get("type") in {"transaction", "event"}:
                self.events.append(item.payload.json)


@pytest.fixture
def traced(monkeypatch, tmp_path):
    from replay.main import create_app

    previous = sentry_sdk.get_global_scope().client
    sentry_sdk.get_global_scope().set_client(None)
    capture = Capture()
    initialize = sentry_sdk.init

    def local_init(**kwargs):
        return initialize(**{**kwargs, "transport": capture})

    monkeypatch.setattr(sentry_sdk, "init", local_init)
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setenv("SENTRY_RELEASE", "kumite-replay@test-release")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "verification-test")
    monkeypatch.setenv("KUMITE_COACH_MODE", "local")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    with TestClient(create_app()) as client:
        yield client, capture
    sentry_sdk.get_client().close()
    sentry_sdk.get_global_scope().set_client(previous)


def provider(monkeypatch, mode="success"):
    from replay import coach

    async def respond(request):
        if mode == "timeout":
            await asyncio.sleep(3)
        if mode == "error":
            return httpx.Response(503, json={"error": {"message":
                f"private-provider-error private-player {EXAMPLE['session_id']} test-secret-api-key"}})
        selected = SELECTED if mode == "success" else "Invented advice"
        return httpx.Response(200, json={
            "id": "resp_test", "object": "response", "created_at": 0,
            "model": "test-model", "status": "completed",
            "output": [{"id": "msg_test", "type": "message", "role": "assistant",
                        "status": "completed", "content": [{"type": "output_text",
                        "text": json.dumps({"text": selected}), "annotations": []}]}],
            "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
            "usage": {"input_tokens": 120, "output_tokens": 18, "total_tokens": 138},
        })

    monkeypatch.setattr(coach, "AsyncOpenAI", lambda **kwargs: AsyncOpenAI(
        **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))))
    return coach.RoundCoach(coach.OpenAIProvider("test-secret-api-key", "test-model"))


def transaction(capture):
    events = [event for event in capture.events if event.get("type") == "transaction"]
    assert len(events) == 1
    return events[0]


def test_http_agent_and_actual_responses_sdk_share_one_trace(traced, monkeypatch):
    client, capture = traced
    client.app.state.coach = provider(monkeypatch)
    response = client.post("/coach/round", json=EXAMPLE)
    assert response.json() == {"text": SELECTED, "severity": "warn"}
    event = transaction(capture)
    assert event["release"] == "kumite-replay@test-release"
    assert event["environment"] == "verification-test"
    assert event["contexts"]["trace"]["op"] == "http.server"
    agent, = [span for span in event["spans"] if span["op"] == "gen_ai.invoke_agent"]
    llm, = [span for span in event["spans"] if span["op"] == "gen_ai.responses"]
    assert llm["parent_span_id"] == agent["span_id"]
    assert llm["trace_id"] == agent["trace_id"] == event["contexts"]["trace"]["trace_id"]
    assert agent["data"]["coach.outcome"] == "provider_selected"
    assert llm["data"]["gen_ai.request.model"] == "test-model"
    assert llm["data"]["gen_ai.usage.input_tokens"] == 120
    assert llm["data"]["gen_ai.usage.output_tokens"] == 18
    assert response.headers["x-sentry-trace-id"] == agent["trace_id"]
    assert event["tags"]["coach.outcome"] == "provider_selected"
    serialized = json.dumps(capture.events)
    for private in ["test-secret-api-key", EXAMPLE["session_id"], SELECTED, "round_summary", "top_habits"]:
        assert private not in serialized


@pytest.mark.parametrize("mode", ["error", "timeout", "invalid"])
def test_failed_provider_is_marked_fallback_even_when_http_succeeds(traced, monkeypatch, mode):
    client, capture = traced
    client.app.state.coach = provider(monkeypatch, mode)
    response = client.post("/coach/round", json=EXAMPLE)
    assert response.status_code == 200
    assert response.json()["text"].startswith("Low-defense trouble")
    event = transaction(capture)
    agent, = [span for span in event["spans"] if span["op"] == "gen_ai.invoke_agent"]
    assert agent["data"]["coach.outcome"] == "fallback"
    assert event["tags"]["coach.outcome"] == "fallback"
    serialized = json.dumps(capture.events)
    for private in ["private-provider-error", "private-player", EXAMPLE["session_id"], "test-secret-api-key"]:
        assert private not in serialized


def test_repeated_app_creation_preserves_existing_sentry_client(traced):
    from replay.main import create_app

    original = sentry_sdk.get_client()
    create_app()
    assert sentry_sdk.get_client() is original


def test_report_route_does_not_expose_session_id_in_http_url(traced):
    client, capture = traced
    assert client.get("/reports/private-player-session").status_code == 404
    assert "private-player-session" not in json.dumps(capture.events)


def test_analytics_breadcrumb_does_not_expose_session_in_later_error(traced):
    client, capture = traced

    async def error_after_learning():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(503))) as upstream:
            await upstream.get("http://127.0.0.1:8767/learning/private-player-session")
        raise RuntimeError("Learning unavailable")

    client.app.add_api_route("/test-error", error_after_learning)
    with pytest.raises(RuntimeError, match="Learning unavailable"):
        client.get("/test-error")
    assert any(event.get("exception") for event in capture.events)
    assert "private-player-session" not in json.dumps(capture.events)


@pytest.mark.parametrize("fixed", [False, True])
def test_local_or_deterministic_tip_never_claims_provider_evidence(traced, monkeypatch, fixed):
    client, capture = traced
    summary = copy.deepcopy(EXAMPLE)
    if fixed:
        client.app.state.coach = provider(monkeypatch)
        summary["newly_fixed"] = ["low_defense"]
    assert client.post("/coach/round", json=summary).status_code == 200
    event = transaction(capture)
    agent, = [span for span in event["spans"] if span["op"] == "gen_ai.invoke_agent"]
    assert agent["data"]["coach.outcome"] == ("deterministic" if fixed else "local")
    assert not any(span["op"] == "gen_ai.responses" for span in event["spans"])


def test_invalid_payload_does_not_start_coaching(traced):
    client, capture = traced
    assert client.post("/coach/round", json={}).status_code == 422
    assert not any(span["op"] == "gen_ai.invoke_agent" for span in transaction(capture)["spans"])


def test_invalid_dsn_does_not_break_local_coaching(monkeypatch):
    from replay.main import create_app

    previous = sentry_sdk.get_global_scope().client
    sentry_sdk.get_global_scope().set_client(None)
    monkeypatch.setenv("SENTRY_DSN", "https://example.invalid/projects/coach")
    monkeypatch.setenv("KUMITE_COACH_MODE", "local")
    try:
        with TestClient(create_app()) as client:
            assert client.post("/coach/round", json=EXAMPLE).status_code == 200
        assert not sentry_sdk.is_initialized()
    finally:
        sentry_sdk.get_global_scope().set_client(previous)
