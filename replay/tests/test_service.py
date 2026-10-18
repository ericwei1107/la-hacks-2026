import asyncio
import copy
import json
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = json.loads((ROOT / "contracts/examples/round_summary.json").read_text())


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("KUMITE_COACH_MODE", "local")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from replay.main import create_app

    with TestClient(create_app()) as instance:
        yield instance


def test_health_reports_version_and_reads_data_dir(client, tmp_path):
    result = client.get("/health")
    assert result.status_code == 200
    assert result.json() == {
        "ok": True,
        "service": "replay",
        "version": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
    }
    assert client.app.state.settings.data_dir == tmp_path


def test_example_returns_grounded_short_tip_within_budget(client):
    started = time.monotonic()
    response = client.post("/coach/round", json=EXAMPLE)
    assert time.monotonic() - started < 8
    assert response.status_code == 200
    result = response.json()
    assert set(result) == {"text", "severity"}
    assert result["severity"] == "warn"
    assert 0 < len(result["text"].split()) < 40
    assert "low" in result["text"].lower()
    assert "crouch" in result["text"].lower()
    assert "7" in result["text"]
    assert "5 of 7" not in result["text"]


@pytest.mark.parametrize("field,value", [("round", 0), ("human_slot", 2), ("winner", True)])
def test_invalid_summary_rejected_against_frozen_schema(client, field, value):
    summary = copy.deepcopy(EXAMPLE)
    summary[field] = value
    assert client.post("/coach/round", json=summary).status_code == 422


def test_missing_fields_and_non_objects_are_rejected(client):
    for payload in [{}, [], None, "round"]:
        assert client.post("/coach/round", json=payload).status_code == 422


def test_unknown_fields_are_accepted(client):
    summary = {**EXAMPLE, "future_field": {"value": 1}}
    assert client.post("/coach/round", json=summary).status_code == 200


def test_fixed_low_defense_is_praised_instead_of_targeted(client):
    summary = copy.deepcopy(EXAMPLE)
    summary["top_habits"][0]["fixed"] = True
    summary["newly_fixed"] = ["low_defense"]
    result = client.post("/coach/round", json=summary).json()
    assert result["severity"] == "praise"
    assert "keep" in result["text"].lower()


def test_sparse_summary_does_not_invent_a_habit(client):
    summary = {**EXAMPLE, "top_habits": [], "biggest_moments": [], "exploited": []}
    result = client.post("/coach/round", json=summary).json()
    assert result["severity"] == "info"
    assert "enough" in result["text"].lower()


def test_successful_defense_is_not_called_a_weakness(client):
    summary = copy.deepcopy(EXAMPLE)
    summary["top_habits"][0]["action"] = "blocked"
    result = client.post("/coach/round", json=summary).json()
    assert result["severity"] != "warn"


def test_desktop_cors_preflight(client):
    response = client.options("/coach/round", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


@pytest.mark.parametrize("failure", ["timeout", "error", "long", "invalid_move"])
def test_model_failure_or_invalid_advice_uses_grounded_fallback(client, monkeypatch, failure):
    from replay.coach import RoundCoach

    async def provider(summary, baseline):
        if failure == "timeout":
            await asyncio.sleep(1)
        if failure == "error":
            raise RuntimeError("private-provider-error")
        if failure == "long":
            return " ".join(["word"] * 40)
        return "Use Imaginary Dragon Punch to win."

    client.app.state.coach = RoundCoach(provider=provider, timeout=0.02)
    started = time.monotonic()
    response = client.post("/coach/round", json=EXAMPLE)
    assert time.monotonic() - started < 1
    assert response.status_code == 200
    assert "crouch" in response.json()["text"].lower()
    assert "private-provider-error" not in response.text


def test_model_can_select_a_grounded_tip(client):
    from replay.coach import RoundCoach

    async def provider(summary, baseline):
        return "You have a low-defense pattern across 7 observations. Practice crouch-blocking predictable lows."

    client.app.state.coach = RoundCoach(provider=provider, timeout=0.1)
    result = client.post("/coach/round", json=EXAMPLE).json()
    assert result["text"].startswith("You have a low-defense pattern")


@pytest.mark.parametrize("observations,probability", [(3, 0.99), (7, 0.4), (0, 1)])
def test_weak_evidence_does_not_become_confident_advice(client, observations, probability):
    summary = copy.deepcopy(EXAMPLE)
    summary["top_habits"][0].update(n=observations, p=probability)
    assert client.post("/coach/round", json=summary).json()["severity"] == "info"


def test_real_sdk_parses_structured_selection_without_external_network(client, monkeypatch):
    from openai import AsyncOpenAI
    from replay import coach

    selected = "You have a low-defense pattern across 7 observations. Practice crouch-blocking predictable lows."

    def handle(request):
        return httpx.Response(200, json={
            "id": "resp_test", "object": "response", "created_at": 0,
            "model": "test-model", "status": "completed",
            "output": [{"id": "msg_test", "type": "message", "role": "assistant",
                        "status": "completed", "content": [{"type": "output_text",
                        "text": json.dumps({"text": selected}), "annotations": []}]}],
            "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
        })

    def make_client(**kwargs):
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))

    monkeypatch.setattr(coach, "AsyncOpenAI", make_client)
    client.app.state.coach = coach.RoundCoach(coach.OpenAIProvider("test-key", "test-model"))
    response = client.post("/coach/round", json=EXAMPLE)
    assert response.status_code == 200
    assert response.json() == {"text": selected, "severity": "warn"}


@pytest.mark.parametrize("situation,action,fixed", [
    ("low_defense", "hit", False), ("throw_break", "none", False),
    ("after_block:b4", "press", False), ("after_block:f4", "press", False),
    ("unknown", "unknown", False), ("low_defense", "hit", True),
])
def test_round_tips_fit_twenty_word_voice_budget(client, situation, action, fixed):
    summary = copy.deepcopy(EXAMPLE)
    summary["top_habits"][0].update(situation=situation, action=action, fixed=fixed)
    result = client.post("/coach/round", json=summary)
    assert result.status_code == 200
    assert 0 < len(result.json()["text"].split()) <= 20


def test_optional_provider_deadline_leaves_time_for_speech(client):
    from replay.coach import RoundCoach

    async def slow_provider(summary, advice):
        await asyncio.sleep(3)
        return advice.tips[0].text

    client.app.state.coach = RoundCoach(provider=slow_provider)
    start = time.monotonic()
    response = client.post("/coach/round", json=EXAMPLE)
    assert time.monotonic() - start < 1.8
    assert response.status_code == 200
    assert len(response.json()["text"].split()) <= 20


def test_single_grounded_tip_does_not_wait_for_model(client):
    from replay.coach import RoundCoach

    calls = []

    async def provider(summary, advice):
        calls.append(summary)
        return advice.tips[0].text

    client.app.state.coach = RoundCoach(provider=provider)
    summary = copy.deepcopy(EXAMPLE)
    summary["biggest_moments"][0]["move_id"] = 0x6DB
    response = client.post("/coach/round", json=summary)
    assert response.status_code == 200
    assert "Crouch Shin Kick" in response.json()["text"]
    assert calls == []


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("field", ["probability", "extension"])
def test_nonfinite_round_numbers_are_rejected_before_coaching(client, value, field):
    summary = copy.deepcopy(EXAMPLE)
    if field == "probability":
        summary["top_habits"][0]["p"] = value
    else:
        summary["future_field"] = {"measurements": [value]}
    response = client.post("/coach/round", content=json.dumps(summary),
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 422


@pytest.mark.parametrize("suffix", ["bot_minus", "any", "unknown", "b4", "0x674"])
def test_after_block_pressing_without_disadvantage_is_not_a_weakness(client, suffix):
    summary = copy.deepcopy(EXAMPLE)
    summary["top_habits"][0].update(situation=f"after_block:{suffix}", action="press")
    summary["biggest_moments"] = []
    response = client.post("/coach/round", json=summary)
    assert response.status_code == 200
    assert response.json()["severity"] == "info"
    assert "guard" not in response.json()["text"].lower()


def test_bot_plus_pressing_retains_grounded_guarding_advice(client):
    summary = copy.deepcopy(EXAMPLE)
    summary["top_habits"][0].update(situation="after_block:bot_plus", action="press")
    summary["biggest_moments"] = []
    response = client.post("/coach/round", json=summary)
    assert response.status_code == 200
    assert response.json()["severity"] == "warn"
    assert "guard" in response.json()["text"].lower()
