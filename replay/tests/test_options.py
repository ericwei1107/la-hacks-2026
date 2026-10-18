import copy
import hashlib
import json
from pathlib import Path

import pytest

from replay.character_data import (
    CHARACTERS_DIR,
    CharacterDataError,
    format_move_id,
    load_character,
    load_matchup,
    normalize_character,
    normalize_command,
    normalize_move_id,
    resolve_move,
)
from replay.options import MAX_OPTIONS, generate_options

ROOT = Path(__file__).resolve().parents[2]
INSPECTION = ROOT / "data/inspections/2026-10-17T23-48-17_sahil_djin_vs_kaz.inspection.json"
OPTION_KEYS = {"id", "name", "command", "description"}


def block_moment(**overrides):
    moment = {
        "kind": "human_block", "human_slot": 0, "actor": 1, "target": 0,
        "move_id": "0x6DB", "hit_level": "low", "recorded_frame_advantage": -15,
        "context": {"distance_bucket": "close", "human": {"character": "devil_jin"},
                    "opponent": {"character": "kazuya"}},
        "evidence": [{"record": {"t": "event", "kind": "block", "frame_advantage": -15,
                                 "detail": {"string_continued": False}}}],
    }
    for key, value in overrides.items():
        moment[key] = value
    return moment


def commands_of(result):
    return [option["command"] for option in result["options"]]


def fingerprint():
    return {path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(CHARACTERS_DIR.rglob("*")) if path.is_file()}


def legal_commands(character):
    data = load_character(character)
    inputs = set(data.options["inputs"].values()) | {"1", "2", "1+2", "n", "d", "block"}
    return set(data.by_command) | set(data.throw_by_command) | inputs


@pytest.mark.parametrize("value,expected", [
    (1711, 1711), ("0x6AF", 1711), ("0X6af", 1711), ("1711", 1711), (" 0x6af ", 1711),
    (0, 0), ("0x0", 0), (-1, None), (True, None), (None, None), ("6AF", None),
    ("0xZZ", None), ("", None), (1.5, None), ([], None),
])
def test_normalize_move_id(value, expected):
    assert normalize_move_id(value) == expected


def test_format_move_id_is_canonical():
    assert format_move_id("0x6af") == "0x6AF"
    assert format_move_id(1711) == "0x6AF"
    assert format_move_id("junk") is None


@pytest.mark.parametrize("value,expected", [
    ("devil_jin", "devil_jin"), ("Devil Jin", "devil_jin"), ("djin", "devil_jin"), ("Kaz", "kazuya"),
    ("KING", "king"), ("shaheen", "shaheen"), (12, "devil_jin"), (8, "kazuya"), (2, "king"),
    (20, "shaheen"), ("jack", None), (None, None), (True, None),
])
def test_normalize_character(value, expected):
    assert normalize_character(value) == expected


@pytest.mark.parametrize("value,expected", [
    ("d/f+1", "df+1"), ("D/B + 3", "db+3"), ("ws+2", "ws2"), ("f, n, d, df+2", "f,n,d,df+2"),
    ("f,n,d,df+2  (electric)", "f,n,d,df+2 (electric)"),
])
def test_normalize_command(value, expected):
    assert normalize_command(value) == expected


def test_move_ids_are_resolved_per_character():
    assert load_character("devil_jin").resolve_move_id("0x6AF").move["command"] == "db+2"
    assert load_character("kazuya").resolve_move_id(0x6AF).move["command"] == "df+2"
    assert load_character("kazuya").resolve_move_id("0x6db").move["command"] == "d+4"


def test_shared_and_unknown_ids_are_not_guessed():
    shared = load_character("kazuya").resolve_move_id("0x5C1")
    assert shared.status == "ambiguous" and shared.move is None and len(shared.candidates) > 1
    assert load_character("kazuya").resolve_move_id(0x8001).status == "unknown"
    assert load_character("devil_jin").resolve_move_id("not-an-id").status == "unknown"
    assert load_character("shaheen").resolve_move_id(0x6AF).status == "unknown"


def test_move_names_aliases_and_notation_resolve():
    kazuya = load_character("kazuya")
    assert kazuya.resolve_move("Hellsweep").move["command"] == "f,n,d,DF+4"
    assert kazuya.resolve_move("f,n,d,df+4").move["command"] == "f,n,d,DF+4"
    assert kazuya.resolve_move("EWGF").move["command"] == "f,n,d,df+2 (electric)"
    assert kazuya.resolve_move("wind god fist").move["command"] == "f,n,d,df+2"
    assert kazuya.resolve_move("d/f+2").move["command"] == "df+2"
    assert kazuya.resolve_move("left throw").move["command"] == "Left throw"
    assert kazuya.resolve_move("1").move["command"] == "1"
    assert kazuya.resolve_move("0x6DB").move["command"] == "d+4"
    assert resolve_move("devil_jin", "Corpse Thrust").move["command"] == "d+1"
    assert kazuya.resolve_move("Not A Move").status == "unknown"
    assert kazuya.resolve_move("").status == "unknown"
    assert kazuya.resolve_move("2").move["command"] == "2"


def test_ambiguous_names_report_candidates():
    for character in ("kazuya", "king", "devil_jin", "shaheen"):
        data = load_character(character)
        names = {}
        for move in data.moves:
            if move.get("name"):
                names.setdefault(move["name"], []).append(move["command"])
        for name, commands in names.items():
            if len(commands) > 1:
                result = data.resolve_move(name)
                assert result.status == "ambiguous" and set(result.candidates) == set(commands)
                return
    pytest.skip("No duplicate move names in the character data")


def test_unknown_character_raises():
    with pytest.raises(CharacterDataError):
        load_character("jack")


def test_matchup_notes_resolve_and_parse():
    notes = load_matchup("devil_jin", "kazuya")
    assert notes.path.name == "kazuya.md" and notes.path.parent.name == "matchups"
    assert notes.expectations
    row = notes.punish_row("d+4")
    assert row is not None and row["Punish with"]
    assert notes.punish_row("not+a+move") is None
    assert load_matchup("Kazuya", "Devil Jin") is not None
    assert load_matchup("kazuya", "king") is None
    assert load_matchup("kazuya", "mystery") is None


def test_punish_tiers_follow_the_gap():
    data = load_character("kazuya")
    assert data.punish_tier(-9) == []
    assert data.punish_tier(5) == []
    assert data.punish_tier(-10) == data.punishers["tiers"]["10"]["standing"]
    assert data.punish_tier(-35, crouching=True) == data.punishers["tiers"]["20"]["crouching"]


def test_character_files_are_not_modified():
    before = fingerprint()
    load_character("kazuya")
    load_matchup("devil_jin", "kazuya")
    generate_options("devil_jin", block_moment())
    generate_options("king", {"kind": "human_knockdown", "human_slot": 0})
    assert fingerprint() == before


def test_punish_is_offered_with_timing_and_range_evidence():
    result = generate_options("devil_jin", block_moment())
    assert set(result) == {"options", "limitations"}
    punishes = [option for option in result["options"] if option["id"].startswith("punish_")]
    assert punishes
    human = load_character("devil_jin")
    allowed = {entry["command"] for entry in human.punish_tier(-15, crouching=True)}
    for option in punishes:
        assert option["command"] in allowed
        assert human.by_command[option["command"]]["startup"] <= 15
        assert "-15" in option["description"] and "Crouch Shin Kick (d+4)" in option["description"]
    assert any("input timing" in note for note in result["limitations"])


def test_standing_list_is_used_for_non_low_non_crouching_moves():
    moment = block_moment(move_id="0x6AF", hit_level="mid", recorded_frame_advantage=-12)
    moment["evidence"][0]["record"]["frame_advantage"] = -12
    result = generate_options("devil_jin", moment)
    commands = [o["command"] for o in result["options"] if o["id"].startswith("punish_")]
    assert commands
    standing = {entry["command"] for entry in load_character("devil_jin").punish_tier(-12)}
    assert set(commands) <= standing


@pytest.mark.parametrize("change,reason", [
    ({"recorded_frame_advantage": -5}, "no guaranteed punish"),
    ({"recorded_frame_advantage": None}, "No recorded frame advantage"),
    ({"context": {"distance_bucket": "far", "human": {"character": "devil_jin"}, "opponent": {"character": "kazuya"}}}, "Distance"),
    ({"context": {"human": {"character": "devil_jin"}, "opponent": {"character": "kazuya"}}}, "Distance"),
    ({"recorded_frame_advantage": -9}, "no guaranteed punish"),
])
def test_punish_is_withheld_without_evidence(change, reason):
    moment = block_moment(**change)
    for record_value in (change.get("recorded_frame_advantage", -15),):
        moment["evidence"][0]["record"]["frame_advantage"] = record_value
    result = generate_options("devil_jin", moment)
    assert not [o for o in result["options"] if o["id"].startswith("punish_")]
    assert any(reason in note for note in result["limitations"])
    assert result["options"]


def test_string_continuation_blocks_a_punish():
    moment = block_moment()
    moment["evidence"][0]["record"]["detail"]["string_continued"] = True
    result = generate_options("devil_jin", moment)
    assert not [o for o in result["options"] if o["id"].startswith("punish_")]
    assert any("string continued" in note for note in result["limitations"])


def test_conflict_with_frame_data_blocks_a_punish():
    moment = block_moment(recorded_frame_advantage=-11)
    moment["evidence"][0]["record"]["frame_advantage"] = -11
    result = generate_options("devil_jin", moment)
    assert not [o for o in result["options"] if o["id"].startswith("punish_")]
    assert any("disagrees" in note for note in result["limitations"])


def test_unknown_opponent_id_is_not_named_or_guessed():
    result = generate_options("devil_jin", block_moment(move_id=0x8001))
    assert any("not a verified kazuya move ID" in note for note in result["limitations"])
    punishes = [o for o in result["options"] if o["id"].startswith("punish_")]
    for option in punishes:
        assert "after " not in option["description"]
        assert "against the blocked move" in option["description"]


def test_shared_opponent_id_is_not_named():
    result = generate_options("devil_jin", block_moment(move_id="0x5C1"))
    assert any("shared by several" in note for note in result["limitations"])
    assert all("after " not in o["description"] for o in result["options"])


def test_unknown_opponent_character_is_reported():
    moment = block_moment(context={"distance_bucket": "close", "human": {"character": "devil_jin"}})
    result = generate_options("devil_jin", moment)
    assert any("opponent's character is not known" in note for note in result["limitations"])


def test_options_use_the_humans_character():
    moment = block_moment()
    for character in ("devil_jin", "kazuya", "king", "shaheen"):
        result = generate_options(character, moment)
        legal = legal_commands(character)
        assert result["options"]
        for option in result["options"]:
            assert option["command"] in legal
    assert commands_of(generate_options("devil_jin", moment)) != commands_of(generate_options("king", moment))
    mismatch = generate_options("kazuya", moment)
    assert any("lists devil_jin as the human's character" in note for note in mismatch["limitations"])


def test_raw_event_shape_is_understood():
    event = {"t": "event", "kind": "block", "actor": 1, "target": 0, "human_slot": 0, "frame": 10, "round": 1,
             "move_id": 1755, "hit_level": "low", "frame_advantage": -15, "detail": {"string_continued": False},
             "context": {"distance_bucket": "point_blank", "human": {"character": "devil_jin"},
                         "opponent": {"character": "kazuya"}}}
    result = generate_options("devil_jin", event)
    assert [o for o in result["options"] if o["id"].startswith("punish_")]
    mirrored = dict(event, actor=0, target=1)
    assert not [o for o in generate_options("devil_jin", mirrored)["options"] if o["id"].startswith("punish_")]


def test_missing_human_slot_gives_no_options():
    event = {"t": "event", "kind": "block", "actor": 1, "target": 0, "move_id": 1755}
    result = generate_options("devil_jin", event)
    assert result["options"] == []
    assert any("cannot be established" in note for note in result["limitations"])


def test_throw_break_options_name_the_listed_break():
    moment = {"kind": "human_thrown", "human_slot": 0, "actor": 1, "target": 0, "move_id": "0x741",
              "context": {"human": {"character": "kazuya"}, "opponent": {"character": "king"}}}
    result = generate_options("kazuya", moment)
    by_id = {option["id"]: option for option in result["options"]}
    assert {"break_1", "break_2", "break_1+2", "no_break"} <= set(by_id)
    assert "break 1 for qcf+1" in by_id["break_1"]["description"]
    assert "character data lists" not in by_id["break_2"]["description"]


def test_throw_break_unknown_is_not_guessed():
    moment = {"kind": "human_thrown", "human_slot": 0, "actor": 1, "target": 0, "move_id": 0x8001,
              "context": {"human": {"character": "kazuya"}, "opponent": {"character": "king"}}}
    result = generate_options("kazuya", moment)
    assert all("character data lists" not in o["description"] for o in result["options"])
    assert any("break input for this throw is not established" in note for note in result["limitations"])


def test_whiff_never_claims_a_punish():
    moment = {"kind": "opponent_whiff", "human_slot": 0, "actor": 1, "move_id": 1755, "distance_bucket": "point_blank",
              "frame_advantage": -20, "context": {"distance_bucket": "point_blank"}}
    result = generate_options("kazuya", moment)
    assert result["options"]
    assert all("punish" not in option["id"] and "whiff_punish" not in option["id"] for option in result["options"])
    assert any("Whiff-punish range and timing are not established" in note for note in result["limitations"])


def test_defence_after_being_hit_follows_the_hit_level():
    low = generate_options("king", {"kind": "human_hit", "hit_level": "low"})
    assert commands_of(low)[0] == "d"
    high = generate_options("king", {"kind": "human_hit", "hit_level": "high"})
    assert commands_of(high)[0] == "d" and "block" in commands_of(high)
    unknown = generate_options("king", {"kind": "human_hit"})
    assert len(unknown["options"]) >= 3


def test_blocked_attack_notes_an_unsafe_move():
    moment = {"kind": "human_attack_blocked", "move_id": 1711, "hit_level": "low",
              "context": {"human": {"character": "devil_jin"}, "opponent": {"character": "kazuya"}}}
    result = generate_options("devil_jin", moment)
    assert any("db+2 is -13 on block" in note for note in result["limitations"])
    assert result["options"]


def test_decision_labels_select_the_menu():
    base = {"kind": "human_decision", "human_slot": 0, "actor": 0,
            "context": {"human": {"character": "kazuya"}, "opponent": {"character": "devil_jin"}}}
    after_block = generate_options("kazuya", dict(base, situation="after_block:df+1"))
    assert "block" in commands_of(after_block) and not any(o["id"].startswith("punish_") for o in after_block["options"])
    assert any("No frame advantage was evaluated" in note for note in after_block["limitations"])
    low = generate_options("kazuya", dict(base, situation="low_defense"))
    assert commands_of(low)[0] == "d"
    throw = generate_options("kazuya", dict(base, situation="throw_break"))
    assert {"1", "2", "1+2", "n"} <= set(commands_of(throw))
    unlabeled = generate_options("kazuya", dict(base, situation="mystery"))
    assert any("does not name a situation" in note for note in unlabeled["limitations"])


def test_knockdown_roles():
    down = generate_options("king", {"kind": "human_knockdown"})
    assert down["options"]
    oki = generate_options("king", {"kind": "opponent_knockdown"})
    assert oki["options"] and all(option["id"].startswith("oki_") for option in oki["options"])


def test_bad_inputs_are_safe():
    assert generate_options("jack", {"kind": "human_hit"})["options"] == []
    assert generate_options("jack", {"kind": "human_hit"})["limitations"]
    for bad in (None, [], "text", 5):
        result = generate_options("kazuya", bad)
        assert result["options"] == [] and result["limitations"]
    assert generate_options("kazuya", {})["options"] == []


def test_option_shape_is_stable():
    for moment in (block_moment(), {"kind": "human_whiff"}, {"kind": "human_knockdown"}):
        result = generate_options("devil_jin", copy.deepcopy(moment))
        assert 0 < len(result["options"]) <= MAX_OPTIONS
        ids = [o["id"] for o in result["options"]]
        commands = commands_of(result)
        assert len(set(ids)) == len(ids) and len(set(commands)) == len(commands)
        for option in result["options"]:
            assert set(option) == OPTION_KEYS
            assert all(isinstance(option[key], str) and option[key] for key in OPTION_KEYS)
        assert all(isinstance(note, str) for note in result["limitations"])
        assert len(set(result["limitations"])) == len(result["limitations"])


@pytest.mark.skipif(not INSPECTION.exists(), reason="inspection output is not available")
def test_real_inspection_moments_produce_valid_options():
    report = json.loads(INSPECTION.read_text(encoding="utf-8"))
    legal = legal_commands("devil_jin")
    for moment in report["moments"]:
        result = generate_options("devil_jin", moment)
        assert len(result["options"]) <= MAX_OPTIONS
        for option in result["options"]:
            assert set(option) == OPTION_KEYS
            assert option["command"] in legal
        assert not [o for o in result["options"] if o["id"].startswith("punish_")] or moment["kind"] == "human_block"
