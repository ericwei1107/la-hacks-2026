import asyncio
import copy
import json
from pathlib import Path

import pytest

from replay.coach import RoundCoach

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = json.loads((ROOT / "contracts/examples/round_summary.json").read_text())


def tip(summary, provider=None):
    return asyncio.run(RoundCoach(provider=provider).coach(summary))


def test_low_tip_names_verified_bot_move():
    summary = copy.deepcopy(EXAMPLE)
    summary["biggest_moments"][0]["move_id"] = 0x6DB
    text = tip(summary).text
    assert "Crouch Shin Kick" in text and "crouch" in text.lower()
    assert len(text.split()) < 40


@pytest.mark.parametrize("suffix,name", [("f4", "Right Splits Kick"), ("0x680", "Right Splits Kick")])
def test_after_block_compact_labels_name_bot_move(suffix, name):
    summary = copy.deepcopy(EXAMPLE)
    summary["top_habits"][0].update(situation=f"after_block:{suffix}", action="press")
    summary["biggest_moments"] = []
    result = tip(summary)
    assert name in result.text
    assert "guard" in result.text.lower()
    assert "guaranteed" not in result.text.lower()


def test_unsupported_after_block_habit_cannot_override_grounded_low_advice():
    summary = copy.deepcopy(EXAMPLE)
    summary["top_habits"].insert(0, {"situation": "after_block:b4", "action": "press", "p": 0.99, "n": 10})
    summary["biggest_moments"][0]["move_id"] = 0x6DB
    result = tip(summary)
    assert "Crouch Shin Kick" in result.text
    assert "Flash Tornado" not in result.text


def test_unverified_and_shared_ids_keep_generic_fallback():
    from replay.character_data import load_character

    bot = load_character("kazuya")
    ambiguous = next((number for number, commands in bot._ids.items() if len(commands) > 1), None)
    summary = copy.deepcopy(EXAMPLE)
    for number in [0xFFFFFF] + ([ambiguous] if ambiguous is not None else []):
        summary["biggest_moments"][0]["move_id"] = number
        result = tip(summary)
        assert "Low-defense trouble" in result.text
        assert "0x" not in result.text


def test_move_from_unrelated_moment_not_used():
    summary = copy.deepcopy(EXAMPLE)
    summary["biggest_moments"][0].update(move_id=0x6DB, situation="throw_break")
    assert "Crouch Shin Kick" not in tip(summary).text


def test_provider_cannot_introduce_unverified_move():
    async def provider(summary, advice):
        return "Use Imaginary Dragon Punch against Crouch Shin Kick."

    summary = copy.deepcopy(EXAMPLE)
    summary["biggest_moments"][0]["move_id"] = 0x6DB
    result = tip(summary, provider)
    assert "Crouch Shin Kick" in result.text and "Imaginary" not in result.text


def test_fixed_habit_uses_natural_spoken_wording():
    summary = copy.deepcopy(EXAMPLE)
    summary["newly_fixed"] = ["low_defense"]
    result = tip(summary)
    assert result.severity == "praise"
    assert "You've fixed your low blocking" in result.text
    assert "marked as improved" not in result.text


def test_throw_label_cannot_name_a_known_non_throw_as_a_throw():
    summary = copy.deepcopy(EXAMPLE)
    summary["top_habits"][0].update(situation="throw_break", action="none")
    summary["biggest_moments"][0].update(situation="throw_break", kind="throw", move_id=0x6DB)
    assert "Crouch Shin Kick" not in tip(summary).text


@pytest.mark.parametrize("actor", [0, 2, True])
def test_explicit_non_bot_actor_is_not_used_to_name_bot_move(actor):
    summary = copy.deepcopy(EXAMPLE)
    summary["biggest_moments"][0].update(move_id=0x6DB, actor=actor)
    assert "Crouch Shin Kick" not in tip(summary).text
