import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATE = json.loads((ROOT / "contracts/examples/gamestate.json").read_text())
SESSION = "test_session"


def state(frame, round=1, human_slot=1, human_health=190, bot_health=190):
    record = copy.deepcopy(STATE)
    record.update(session_id=SESSION, frame=frame, round=round, human_slot=human_slot)
    for player in record["players"]:
        player["health"] = human_health if player["slot"] == human_slot else bot_health
    record["players"].reverse()
    return record


def event(kind, frame, round=1, **fields):
    return {"t": "event", "session_id": SESSION, "round": round,
            "frame": frame, "kind": kind, **fields}


def recording(tmp_path, records, tail=""):
    path = tmp_path / "sample.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records) + tail, encoding="utf-8")
    from replay.reader import read_recording

    return read_recording(path)


def inspect(tmp_path, records):
    from replay.inspection import build_inspection

    return build_inspection(recording(tmp_path, records))


def test_reader_preserves_line_citations_and_ignores_unknown_types(tmp_path):
    result = recording(tmp_path, [state(0), {"t": "future_type", "secret": "ignored"},
                                  event("hit", 1, actor=0, target=1, damage=12)])
    assert [r.line for r in result.records] == [1, 3]
    assert result.counts["future_type"] == 1
    assert result.session_id == SESSION


def test_reader_tolerates_only_unterminated_truncated_tail(tmp_path):
    result = recording(tmp_path, [state(0)], tail='{"t":"event",')
    assert len(result.records) == 1
    assert any("truncated" in issue.lower() for issue in result.warnings)
    with pytest.raises(ValueError, match="line 2"):
        recording(tmp_path, [state(0)], tail='{"t":"event",\n')
    with pytest.raises(ValueError, match="line 2"):
        recording(tmp_path, [state(0)], tail='invalid\n' + json.dumps(state(2)))


def test_reader_rejects_invalid_known_schema_and_mixed_sessions(tmp_path):
    with pytest.raises(ValueError, match="line 1"):
        recording(tmp_path, [{"t": "state", "session_id": SESSION}])
    with pytest.raises(ValueError, match="session"):
        recording(tmp_path, [state(0), {**state(1), "session_id": "other"}])


def test_malformed_final_object_is_not_mistaken_for_a_truncated_write(tmp_path):
    with pytest.raises(ValueError, match="line 2"):
        recording(tmp_path, [state(0)], tail='{"t":invalid}')


def test_unterminated_string_tail_is_tolerated(tmp_path):
    result = recording(tmp_path, [state(0)], tail='{"t":"eve')
    assert len(result.records) == 1
    assert result.warnings


@pytest.mark.parametrize("tail", [
    '{"t":"event","frame":1e',
    '{"t":"event","frame":1e+',
    '{"t":"event","frame":1.',
    '{"t":"event","damage":-',
    '{"t":"event","situation":"a\\u12',
])
def test_partial_numeric_and_unicode_tail_preserves_completed_records(tmp_path, tail):
    result = recording(tmp_path, [state(0)], tail=tail)
    assert len(result.records) == 1
    assert len(result.warnings) == 1


@pytest.mark.parametrize("tail", [
    '{"t":"event","situation":"a\\uXYZ',
    '{"t":"event","frame":1eBAD',
])
def test_invalid_numeric_and_unicode_tail_is_not_silently_discarded(tmp_path, tail):
    with pytest.raises(ValueError, match="line 2"):
        recording(tmp_path, [state(0)], tail=tail)


def test_bot_sources_never_supply_human_actions(tmp_path):
    records = [state(0), event("hit", 1, actor=0, target=1, damage=12)]
    for source in ["reflex", "default", "future_source"]:
        records.append({"t": "tactical", "session_id": SESSION, "round": 1,
                        "frame": 1, "source": source, "chosen": "launch"})
    report = inspect(tmp_path, records)
    assert report["tactical_sources"] == {"reflex": 1, "default": 1, "future_source": 1}
    assert len(report["moments"]) == 1
    assert report["moments"][0]["human_action"] is None


def test_human_slot_and_event_roles_are_not_assumed(tmp_path):
    report = inspect(tmp_path, [state(0),
        event("block", 1, actor=1, target=0, frame_advantage=-13, damage=4),
        event("block", 2, actor=0, target=1, frame_advantage=-6),
        event("whiff", 3, actor=0),
        event("whiff", 4, actor=1),
        event("hit", 5, actor=0, target=1, damage=12)])
    assert [m["kind"] for m in report["moments"]] == [
        "human_attack_blocked", "human_block", "opponent_whiff", "human_whiff", "human_hit"]
    blocked = report["moments"][1]
    assert blocked["context"]["human"]["slot"] == 1
    assert blocked["human_action"] is None
    assert blocked["context"]["state_frame"] == 0


def test_explicit_human_decisions_preserve_labels_without_bot_contamination(tmp_path):
    report = inspect(tmp_path, [state(0),
        event("decision_point", 3, actor=1, situation="after_block:df1", action="duck"),
        event("decision_point", 4, actor=0, situation="neutral", action="launch")])
    assert len(report["moments"]) == 1
    moment = report["moments"][0]
    assert moment["kind"] == "human_decision"
    assert moment["situation"] == "after_block:df1"
    assert moment["human_action"] == "duck"
    assert moment["evidence"][0]["line"] == 2


def test_unknown_identity_stays_unknown(tmp_path):
    report = inspect(tmp_path, [event("hit", 5, actor=0, target=1, damage=12)])
    moment = report["moments"][0]
    assert moment["human_slot"] is None
    assert moment["kind"] == "unattributed_event"
    assert moment["outcome"]["human_health_loss"] is None
    assert "human identity" in " ".join(moment["missing_information"]).lower()


def test_future_state_is_not_used_as_context(tmp_path):
    report = inspect(tmp_path, [event("hit", 5, actor=0, target=1), state(6)])
    moment = report["moments"][0]
    assert moment["context"] is None
    assert moment["event_damage"] is None
    assert moment["outcome"]["human_health_loss"] is None


def test_health_loss_window_is_round_local_and_separate_from_event_damage(tmp_path):
    records = [state(f, human_health=190 if f < 5 else 178, bot_health=190 if f < 8 else 183)
               for f in range(61)]
    records += [event("hit", 0, actor=0, target=1, damage=12), state(0, round=2, human_health=20)]
    moment = inspect(tmp_path, records)["moments"][0]
    assert moment["event_damage"] == 12
    assert moment["outcome"]["human_health_loss"] == 12
    assert moment["outcome"]["bot_health_loss"] == 7
    assert moment["outcome"]["coverage_complete"] is True
    assert moment["outcome"]["end_frame"] == 60


def test_round_end_truncates_window_and_marks_incomplete_coverage(tmp_path):
    records = [state(f) for f in range(0, 6)]
    records += [event("whiff", 4, actor=0), event("round_end", 5),
                state(6, human_health=1), state(0, round=2)]
    outcome = inspect(tmp_path, records)["moments"][0]["outcome"]
    assert outcome["end_frame"] == 5
    assert outcome["window_complete"] is False
    assert outcome["human_health_loss"] == 0


def test_gaps_and_health_resets_do_not_yield_exact_damage_claims(tmp_path):
    report = inspect(tmp_path, [state(0, human_health=100), state(2, human_health=120),
                               state(60, human_health=90), event("hit", 0, actor=0, target=1)])
    outcome = report["moments"][0]["outcome"]
    assert outcome["coverage_complete"] is False
    assert outcome["health_increase_observed"] is True
    assert outcome["human_health_loss"] is None


def test_duplicate_frames_do_not_produce_reliable_damage_totals(tmp_path):
    records = [state(f) for f in range(61)] + [state(4, human_health=180),
               event("hit", 0, actor=0, target=1, damage=10)]
    outcome = inspect(tmp_path, records)["moments"][0]["outcome"]
    assert outcome["coverage_complete"] is False
    assert outcome["human_health_loss"] is None


def test_missing_decision_action_stays_unknown_and_throw_break_roles_are_correct(tmp_path):
    report = inspect(tmp_path, [state(0), event("decision_point", 1, actor=1),
        event("throw", 2, actor=0, target=1, detail={"break": "press_2"}),
        event("throw_break", 3, actor=1, target=0, detail={"input": "press_2"})])
    assert [m["kind"] for m in report["moments"]] == ["human_decision", "human_thrown", "human_throw_break"]
    assert report["moments"][0]["human_action"] is None
    assert report["moments"][1]["human_action"] is None


def test_changed_human_slot_explains_suppressed_damage_totals(tmp_path):
    records = [state(f, human_slot=1 if f < 5 else 0) for f in range(61)]
    records.append(event("hit", 0, actor=0, target=1, damage=12))
    moment = inspect(tmp_path, records)["moments"][0]
    assert moment["outcome"]["human_health_loss"] is None
    assert any("human slot changes" in item.lower() for item in moment["missing_information"])


def test_health_window_has_auditable_state_boundary_lines(tmp_path):
    records = [state(f) for f in range(61)] + [event("hit", 0, actor=0, target=1)]
    outcome = inspect(tmp_path, records)["moments"][0]["outcome"]
    assert outcome["state_evidence"] == {"first": {"line": 1, "frame": 0},
                                         "last": {"line": 61, "frame": 60}}


def test_output_escapes_markdown_and_protects_existing_files(tmp_path):
    from replay.inspection import write_inspection

    report = inspect(tmp_path, [state(0), event("decision_point", 1, actor=1,
        situation="<script>alert(1)</script>", action="[click](https://evil.invalid)")])
    report["session_id"] = "../../unsafe"
    json_path, markdown_path = write_inspection(report, tmp_path / "out")
    assert json_path.parent == tmp_path / "out"
    text = markdown_path.read_text(encoding="utf-8")
    assert "<script>" not in text
    assert "[click](https://evil.invalid)" not in text
    with pytest.raises(FileExistsError):
        write_inspection(report, tmp_path / "out")


def test_cli_writes_real_report_without_external_calls(tmp_path):
    source = tmp_path / "source.jsonl"
    source.write_text(json.dumps(state(0)) + "\n" + json.dumps(event("hit", 1, actor=0, target=1, damage=12)) + "\n")
    result = subprocess.run([sys.executable, "-m", "replay.inspect", str(source),
                             "--output-dir", str(tmp_path / "out")], cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    reports = list((tmp_path / "out").glob("*.json"))
    assert len(reports) == 1
    assert json.loads(reports[0].read_text())["moments"][0]["event_damage"] == 12


def test_cli_uses_data_dir_and_explains_zip_input(tmp_path):
    import os

    source = tmp_path / "source.jsonl"
    source.write_text(json.dumps(state(0)) + "\n")
    env = {**os.environ, "DATA_DIR": str(tmp_path / "data")}
    result = subprocess.run([sys.executable, "-m", "replay.inspect", str(source)],
                             cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "data/inspections/test_session.inspection.json").exists()
    result = subprocess.run([sys.executable, "-m", "replay.inspect", "sample.zip"],
                             cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 1
    assert "Extract the ZIP" in result.stderr


def test_real_sample_remains_an_observation_report():
    from replay.reader import read_recording
    from replay.inspection import build_inspection

    sample = ROOT / "data/samples/versus_djin_vs_kaz_l3/versus_djin_vs_kaz_l3.jsonl"
    if not sample.exists():
        pytest.skip("Downloaded sample is local and optional in other checkouts")
    report = build_inspection(read_recording(sample))
    assert report["record_counts"]["state"] == 15108
    assert report["tactical_sources"] == {"reflex": 281}
    assert not any(m["kind"] in {"human_block", "opponent_whiff", "human_decision"}
                   for m in report["moments"])
    assert all(m["human_action"] is None for m in report["moments"])
    assert len([m for m in report["moments"] if m["kind"] == "human_hit"]) == 59


@pytest.mark.parametrize("field", ["human_slot", "health", "distance"])
def test_conflicting_coordinate_retains_event_without_human_attribution(tmp_path, field):
    first = state(10)
    conflicting = copy.deepcopy(first)
    if field == "human_slot":
        conflicting["human_slot"] = 0
    elif field == "health":
        conflicting["players"][0]["health"] -= 1
    else:
        conflicting["derived"]["distance_mm"] += 1
    decision = event("decision_point", 10, actor=1, situation="low_defense", action="hit")
    moment, = inspect(tmp_path, [first, decision, conflicting])["moments"]
    assert moment["kind"] == "unattributed_event"
    assert moment["human_slot"] is None and moment["context"] is None
    assert moment["human_action"] is None
    assert moment["evidence"][0]["record"] == decision
    assert moment["outcome"]["human_health_loss"] is None
    assert "conflicting" in " ".join(moment["missing_information"]).lower()


def test_identical_coordinate_duplicates_preserve_human_attribution(tmp_path):
    snapshot = state(10)
    decision = event("decision_point", 10, actor=1, situation="low_defense", action="hit")
    moment, = inspect(tmp_path, [snapshot, copy.deepcopy(snapshot), decision])["moments"]
    assert moment["kind"] == "human_decision" and moment["human_action"] == "hit"
    assert not any("conflicting" in value.lower() for value in moment["missing_information"])
