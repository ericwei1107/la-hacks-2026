import pytest

from replay.tips import Candidate, validate_text, vocabulary

VOCAB = vocabulary("devil_jin", "kazuya")


def candidate():
    return Candidate(
        topic="low_defense",
        text="Sliding Low Kick (db+3) is a low; it hit you 4 times for 62. Crouch-block it, then punish with d+2.",
        severity="warn", damage=62, strength=0.8,
        moves=["Sliding Low Kick", "db+3", "Crouch Straight", "d+2"],
        numbers=[4, 62, -12, 8],
        detail={"opponent_move": {"name": "Sliding Low Kick", "command": "db+3", "on_block": -12}},
    )


def test_templated_text_passes():
    assert validate_text(candidate().text, ["Sliding Low Kick", "d+2"], candidate(), VOCAB) is None


def test_rewritten_text_with_same_facts_passes():
    text = "Kazuya's Sliding Low Kick hit you 4 times for 62 damage. Crouch-block it and punish with d+2."
    assert validate_text(text, ["Sliding Low Kick", "d+2"], candidate(), VOCAB) is None


def test_on_block_number_may_be_written_as_negative_or_positive():
    assert validate_text("Sliding Low Kick is -12 on block, so punish with d+2.", [], candidate(), VOCAB) is None
    assert validate_text("Sliding Low Kick leaves them 12 frames minus: punish with d+2.", [], candidate(), VOCAB) is None


def test_empty_text_rejected():
    assert validate_text("", [], candidate(), VOCAB) == "empty"
    assert validate_text("   ", [], candidate(), VOCAB) == "empty"


def test_text_over_thirty_words_rejected():
    assert validate_text(" ".join(["block"] * 31), [], candidate(), VOCAB) == "too long"


def test_hallucinated_move_name_in_moves_list_rejected():
    assert validate_text(candidate().text, ["Hellsweep"], candidate(), VOCAB).startswith("unknown move")


def test_hallucinated_real_move_name_in_text_rejected():
    text = "Sliding Low Kick hit you 4 times. Duck and answer with Electric Wind God Fist."
    assert validate_text(text, [], candidate(), VOCAB).startswith("ungrounded move name")


def test_other_character_move_name_in_text_rejected():
    text = "Sliding Low Kick hit you 4 times; punish with Abolishing Fist instead."
    assert validate_text(text, [], candidate(), VOCAB).startswith("ungrounded move name")


def test_hallucinated_command_rejected():
    text = "Sliding Low Kick hit you 4 times for 62. Crouch-block it and punish with b+1+3."
    assert validate_text(text, [], candidate(), VOCAB) == "ungrounded command"


def test_hallucinated_while_standing_command_rejected():
    text = "Sliding Low Kick hit you 4 times. Punish it with ws2 every time."
    assert validate_text(text, [], candidate(), VOCAB) == "ungrounded command"


def test_hallucinated_string_command_rejected():
    text = "Sliding Low Kick hit you 4 times. Answer with 1,1,2 for a launch."
    assert validate_text(text, [], candidate(), VOCAB) == "ungrounded command"


def test_hex_move_id_rejected():
    text = "Move 0x6c6 hit you 4 times for 62. Crouch-block it."
    assert validate_text(text, [], candidate(), VOCAB) == "ungrounded command"


def test_hallucinated_count_rejected():
    text = "Sliding Low Kick hit you 7 times for 62. Crouch-block it, then punish with d+2."
    assert validate_text(text, [], candidate(), VOCAB) == "ungrounded number 7"


def test_hallucinated_damage_rejected():
    text = "Sliding Low Kick hit you 4 times for 90 damage. Crouch-block it, then punish with d+2."
    assert validate_text(text, [], candidate(), VOCAB) == "ungrounded number 90"


def test_hallucinated_frame_data_rejected():
    text = "Sliding Low Kick is -15 on block; punish with d+2 for 8."
    assert validate_text(text, [], candidate(), VOCAB) == "ungrounded number -15"


def test_hallucinated_startup_rejected():
    text = "Sliding Low Kick is a 19 frame low. Crouch-block it, then punish with d+2."
    assert validate_text(text, [], candidate(), VOCAB) == "ungrounded number 19"


def test_decimal_number_rejected():
    text = "Sliding Low Kick hit you 4 times for 62.5. Crouch-block it."
    assert validate_text(text, [], candidate(), VOCAB) == "ungrounded number 62.5"


def test_digits_inside_grounded_commands_are_not_counted_as_numbers():
    text = "Crouch-block db+3, then punish with d+2."
    assert validate_text(text, ["db+3", "d+2"], candidate(), VOCAB) is None


def test_bare_digit_command_in_moves_must_be_grounded():
    throw = Candidate("throw_break", "Double High Sweep (1+3) landed twice. Break it with 2.", "warn",
                      moves=["Double High Sweep", "1+3", "2"], numbers=[2, 70])
    assert validate_text("Double High Sweep landed twice; press 2 as the grab starts.", ["2"], throw, VOCAB) is None
    assert validate_text("Double High Sweep landed twice; press 1+2 as the grab starts.", ["1+2"], throw, VOCAB).startswith("unknown move")


def test_mixed_case_grounded_name_and_command_pass():
    text = "SLIDING LOW KICK (DB+3) hit you 4 times for 62; crouch-block it, then punish with D+2."
    assert validate_text(text, ["sliding low kick", "DB+3", "d+2"], candidate(), VOCAB) is None


def test_non_string_move_entry_rejected():
    assert validate_text(candidate().text, [7], candidate(), VOCAB).startswith("unknown move")


def test_non_string_text_rejected():
    assert validate_text(None, [], candidate(), VOCAB) == "empty"


@pytest.mark.parametrize("text", [
    "Sliding Low Kick hit you 4 times for 62. Crouch-block it, then punish with d+2 or Hook.",
    "After Sliding Low Kick, use Flash Tornado to punish.",
])
def test_grounded_text_with_one_extra_vocabulary_move_rejected(text):
    assert validate_text(text, [], candidate(), VOCAB).startswith("ungrounded move name")
