import asyncio
import json
from types import SimpleNamespace

import pytest

from replay import claude_provider
from replay.chat import AnswerPlan
from replay.coach import Advice, CoachTip, Composition, RoundCoach
from replay.config import Settings
from replay.tips import Candidate


class FakeMessages:
    def __init__(self, log, reply, stop_reason="end_turn", beta_error=False):
        self.log = log
        self.reply = reply
        self.stop_reason = stop_reason
        self.beta_error = beta_error

    async def create(self, **request):
        if "fallbacks" in request and self.beta_error:
            import httpx2

            response = httpx2.Response(400, request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
            raise claude_provider.anthropic.BadRequestError("no fallbacks", response=response, body=None)
        self.log.append(request)
        return SimpleNamespace(stop_reason=self.stop_reason,
                               content=[SimpleNamespace(type="text", text=json.dumps(self.reply))])


class FakeClient:
    def __init__(self, log, reply, stop_reason="end_turn", beta_error=False):
        self.messages = FakeMessages(log, reply, stop_reason, beta_error)
        self.beta = SimpleNamespace(messages=FakeMessages(log, reply, stop_reason, beta_error))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def fake_anthropic(monkeypatch, reply, stop_reason="end_turn", beta_error=False):
    log = []
    monkeypatch.setattr(claude_provider.anthropic, "AsyncAnthropic",
                        lambda **kwargs: FakeClient(log, reply, stop_reason, beta_error))
    return log


def candidate_advice():
    candidate = Candidate("throw_break", "Double High Sweep (1+3) landed 3 times. Break it with 2: press 2 as the grab starts.",
                          "warn", 105, 1.0, ["Double High Sweep", "1+3", "2"], [3, 105, 3])
    return Advice((CoachTip(text=candidate.text, severity="warn"),), (candidate,))


def test_round_provider_composes_with_structured_output_and_low_effort(monkeypatch):
    log = fake_anthropic(monkeypatch, {"text": "Double High Sweep grabbed you 3 times. Press 2 as the grab starts.", "moves": ["2"]})
    result = asyncio.run(claude_provider.ClaudeRoundProvider()(json.loads('{"round": 1}'), candidate_advice()))
    assert isinstance(result, Composition) and result.moves == ["2"]
    request = log[0]
    assert request["model"] == "claude-haiku-5-5"
    assert request["output_config"]["effort"] == "low"
    assert request["output_config"]["format"]["schema"]["required"] == ["text", "moves"]
    assert "fallbacks" not in request
    assert "Double High Sweep" in request["messages"][0]["content"]


def test_round_provider_selects_a_prepared_tip_when_there_is_no_evidence(monkeypatch):
    tips = (CoachTip(text="Tip one about lows.", severity="warn"), CoachTip(text="Tip two about lows.", severity="warn"))
    log = fake_anthropic(monkeypatch, {"text": "Tip two about lows."})
    result = asyncio.run(claude_provider.ClaudeRoundProvider()({"round": 1}, Advice(tips)))
    assert result == "Tip two about lows."
    assert log[0]["output_config"]["format"]["schema"]["properties"]["text"]["enum"] == ["Tip one about lows.", "Tip two about lows."]


def test_refusal_becomes_a_fallback_to_the_templated_tip(monkeypatch):
    fake_anthropic(monkeypatch, {"text": "anything", "moves": []}, stop_reason="refusal")
    coach = RoundCoach(provider=claude_provider.ClaudeRoundProvider())
    summary = {"session_id": "s", "round": 1, "top_habits": [], "biggest_moments": [], "human_slot": 0}
    advice = candidate_advice()
    tip, source = None, None
    try:
        asyncio.run(claude_provider.ClaudeRoundProvider()(summary, advice))
    except ValueError as error:
        assert "declined" in str(error)
    else:
        pytest.fail("a refusal must raise so the coach falls back")
    assert coach.provider is not None


def test_chat_provider_uses_opus_with_fallbacks_and_returns_a_plan(monkeypatch):
    log = fake_anthropic(monkeypatch, {"fact_ids": ["abc"], "text": "Hold down-back.", "moves": []})
    request = SimpleNamespace(message="What should I practice?", history=[], session_id="s")
    tools = SimpleNamespace(notes=lambda: ["Weakness: lows"], characters={"devil_jin", "kazuya"}, synthetic=False)
    plan = asyncio.run(claude_provider.ClaudeChatProvider()(request, tools, [{"id": "abc", "text": "fact"}]))
    assert isinstance(plan, AnswerPlan) and plan.fact_ids == ["abc"] and plan.text == "Hold down-back."
    assert log[0]["model"] == "claude-opus-5-5"
    assert log[0]["fallbacks"] == "default" and log[0]["betas"] == [claude_provider.FALLBACK_BETA]
    assert "Weakness: lows" in log[0]["messages"][0]["content"]


def test_chat_provider_retries_without_fallbacks_when_the_api_rejects_them(monkeypatch):
    log = fake_anthropic(monkeypatch, {"fact_ids": ["abc"], "text": "Hold down-back.", "moves": []}, beta_error=True)
    request = SimpleNamespace(message="q", history=[], session_id="s")
    tools = SimpleNamespace(notes=lambda: [], characters=set(), synthetic=False)
    plan = asyncio.run(claude_provider.ClaudeChatProvider()(request, tools, [{"id": "abc", "text": "fact"}]))
    assert plan.fact_ids == ["abc"]
    assert len(log) == 1 and "fallbacks" not in log[0]


@pytest.mark.parametrize("env,expected", [
    ({"ANTHROPIC_API_KEY": "k"}, "anthropic"),
    ({"ANTHROPIC_API_KEY": "k", "OPENAI_API_KEY": "o"}, "anthropic"),
    ({"OPENAI_API_KEY": "o"}, "openai"),
    ({"ANTHROPIC_API_KEY": "k", "KUMITE_LLM": "openai"}, "local"),
    ({"ANTHROPIC_API_KEY": "k", "KUMITE_COACH_MODE": "local"}, "local"),
    ({}, "local"),
])
def test_settings_pick_the_model_provider(monkeypatch, env, expected):
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "KUMITE_LLM", "KUMITE_COACH_MODE"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("KUMITE_VERSION", "test")
    assert Settings.load().llm == expected


def test_app_uses_claude_when_the_key_is_present(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KUMITE_COACH_MODE", "auto")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("KUMITE_VERSION", "test")
    from replay.main import create_app

    app = create_app()
    assert isinstance(app.state.coach.provider, claude_provider.ClaudeRoundProvider)
    assert isinstance(app.state.chat.provider, claude_provider.ClaudeChatProvider)
