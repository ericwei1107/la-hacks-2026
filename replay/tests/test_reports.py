import copy
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from replay.main import create_app

ROOT = Path(__file__).resolve().parents[2]
STATE = json.loads((ROOT / "contracts/examples/gamestate.json").read_text())
SCHEMA = json.loads((ROOT / "contracts/report.schema.json").read_text())
OPTIONS = [{"id": "guard", "name": "Low guard", "command": "d/b", "description": "Guard low"},
           {"id": "step", "name": "Step left", "command": "u", "description": "Sidestep left"}]


def generate(character, moment):
    assert character == "kazuya"
    assert moment["human_action"] == "hit"
    return {"options": copy.deepcopy(OPTIONS), "limitations": ["Range is not measured precisely"]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KUMITE_COACH_MODE", "local")
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    state = copy.deepcopy(STATE)
    state.update(session_id="test_session", human_slot=1, frame=10)
    state["players"].reverse()
    records = [state, {"t": "event", "session_id": "test_session", "round": 1, "frame": 10,
                       "kind": "decision_point", "actor": 1, "situation": "low_defense", "action": "hit"},
               {"t": "tactical", "session_id": "test_session", "round": 1, "frame": 11,
                "source": "habit", "chosen": "bot_choice"}]
    folder = tmp_path / "recordings"
    folder.mkdir()
    (folder / "test_session.jsonl").write_text("\n".join(map(json.dumps, records)) + "\n")
    app = create_app()
    from replay.scoring import JevScorer

    app.state.reports.scorer = JevScorer("")
    with TestClient(app) as result:
        yield result


def test_analysis_preserves_actions_and_persists_contract_report(client):
    assert client.get("/reports/test_session").status_code == 404
    response = client.post("/analyze/test_session")
    assert response.status_code == 200
    report = response.json()
    Draft202012Validator(SCHEMA).validate(report)
    point, = report["decision_points"]
    assert point["actual"] == "hit"
    assert (point["round"], point["frame"]) == (1, 10)
    assert point["evidence"][0]["line"] == 2
    assert point["options"] == []
    assert point["best"] == "unavailable"
    assert point["scoring"]["status"] == "unavailable"
    assert "good" not in point and "cost" not in point
    assert report["result"] == "unknown"
    assert client.get("/reports/test_session").json() == report
    assert "round_summary" in " ".join(report["limitations"])


def test_jev_http_request_and_report_use_human_options(client):
    from replay.scoring import JevScorer

    def respond(request):
        assert str(request.url) == "https://api.typesafe.ai/v1/systemone"
        payload = json.loads(request.content)
        assert payload["model"] == "jev-latest"
        assert payload["questions"]["d0"]["criteria"] == {
            "guard": "Low guard: Guard low (d/b)", "step": "Step left: Sidestep left (u)"}
        assert "outcome" not in json.loads(payload["state"])["d0"]
        return httpx.Response(200, json={"model": "jev-test", "answers": {"d0": {
            "type": "choice", "choice": "guard", "confidence": 0.4,
            "probabilities": {"guard": 0.7, "step": 0.3}}}})

    service = client.app.state.reports
    service.option_generator = generate
    service.scorer = JevScorer("test-key", transport=httpx.MockTransport(respond))
    report = client.post("/analyze/test_session").json()
    Draft202012Validator(SCHEMA).validate(report)
    point, = report["decision_points"]
    assert point["actual"] == "hit"
    assert point["best"] == "Low guard"
    assert [option["p"] for option in point["options"]] == [0.7, 0.3]
    assert point["scoring"]["status"] == "scored"
    assert "good" not in point
    assert point["limitations"] == ["Range is not measured precisely"]


@pytest.mark.parametrize("answer", [
    {"choice": "guard", "probabilities": {"guard": 0.7}},
    {"choice": "invented", "probabilities": {"guard": 0.7, "step": 0.3}},
    {"choice": "step", "probabilities": {"guard": 0.7, "step": 0.3}},
    {"choice": "guard", "probabilities": {"guard": 0.9, "step": 0.9}},
    {"choice": "guard", "probabilities": {"guard": True, "step": 0}},
    {"choice": "guard", "probabilities": {"guard": -0.1, "step": 1.1}},
])
def test_invalid_jev_distribution_is_not_repaired(client, answer):
    from replay.scoring import JevScorer

    answer["type"] = "choice"
    client.app.state.reports.option_generator = generate
    client.app.state.reports.scorer = JevScorer("test", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"answers": {"d0": answer}})))
    point, = client.post("/analyze/test_session").json()["decision_points"]
    assert point["best"] == "unavailable" and point["options"] == []
    assert point["scoring"]["status"] == "unavailable"


def test_provider_error_does_not_leak_or_fabricate(client):
    from replay.scoring import JevScorer

    client.app.state.reports.option_generator = generate
    client.app.state.reports.scorer = JevScorer("secret-key", transport=httpx.MockTransport(
        lambda request: httpx.Response(401, text="secret-key rejected")))
    response = client.post("/analyze/test_session")
    assert response.status_code == 200
    assert "secret-key" not in response.text
    assert response.json()["decision_points"][0]["options"] == []


def test_missing_recording_and_unsafe_session_id(client):
    assert client.post("/analyze/missing").status_code == 404
    assert client.post("/analyze/bad%5Cname").status_code == 422
    assert client.get("/reports/bad%5Cname").status_code == 422


def test_recording_session_must_match_filename(client):
    path = client.app.state.settings.data_dir / "recordings/test_session.jsonl"
    path.write_text(path.read_text().replace("test_session", "other_session"))
    assert client.post("/analyze/test_session").status_code == 422


def test_stale_context_not_scored(client):
    path = client.app.state.settings.data_dir / "recordings/test_session.jsonl"
    rows = [json.loads(row) for row in path.read_text().splitlines()]
    rows[1]["frame"] = 12
    path.write_text("\n".join(map(json.dumps, rows)))
    client.app.state.reports.option_generator = generate
    point, = client.post("/analyze/test_session").json()["decision_points"]
    assert point["actual"] == "hit" and point["options"] == []
    assert "older" in " ".join(point["missing_information"])


def test_missing_actions_not_inferred_from_tactical_records(client):
    path = client.app.state.settings.data_dir / "recordings/test_session.jsonl"
    rows = [json.loads(row) for row in path.read_text().splitlines()]
    del rows[1]["action"]
    path.write_text("\n".join(map(json.dumps, rows)))
    report = client.post("/analyze/test_session").json()
    point, = report["decision_points"]
    assert point["actual"] == "unknown"
    assert point["recorded_action"] is None
    assert report["habits"] == []


def test_corrupt_saved_report_rejected(client):
    directory = client.app.state.settings.data_dir / "reports"
    directory.mkdir()
    (directory / "test_session.json").write_text('{"session_id":"test_session"}')
    assert client.get("/reports/test_session").status_code == 422


def test_local_jev_mode_does_not_use_environment_key(monkeypatch):
    from replay.scoring import JevScorer

    monkeypatch.setenv("KUMITE_JEV_MODE", "local")
    monkeypatch.setenv("TYPESAFE_API_KEY", "must-not-be-used")
    assert JevScorer.from_env().api_key == ""


def test_sample_discovery_labels_synthetic_and_checks_metadata(client):
    root = client.app.state.settings.data_dir
    sample = root / "samples/synthetic/friendly.jsonl"
    sample.parent.mkdir(parents=True)
    (root / "recordings/test_session.jsonl").replace(sample)
    metadata = json.loads((ROOT / "contracts/examples/session.json").read_text())
    metadata.update(session_id="test_session", result="synthetic loss", mode="synthetic")
    sample.with_suffix(".session.json").write_text(json.dumps(metadata))
    report = client.post("/analyze/test_session").json()
    assert report["synthetic"] is True and report["result"] == "synthetic loss"
    assert "SYNTHETIC" in " ".join(report["limitations"])
    sample.with_suffix(".session.json").write_text(json.dumps({**metadata, "session_id": "wrong"}))
    report = client.post("/analyze/test_session").json()
    assert report["result"] == "unknown"


def test_missing_generator_and_duplicate_option_ids_are_explicit(client):
    def missing(character, moment):
        raise ModuleNotFoundError("private filesystem path")

    client.app.state.reports.option_generator = missing
    response = client.post("/analyze/test_session")
    assert "private filesystem" not in response.text
    point, = response.json()["decision_points"]
    assert point["options"] == [] and "generator" in point["scoring"]["reason"]
    client.app.state.reports.option_generator = lambda *args: {
        "options": [OPTIONS[0], OPTIONS[0]], "limitations": []}
    point, = client.post("/analyze/test_session").json()["decision_points"]
    assert point["candidates"] == []


def test_bot_decisions_excluded_and_unknown_actor_retained(client):
    path = client.app.state.settings.data_dir / "recordings/test_session.jsonl"
    rows = [json.loads(row) for row in path.read_text().splitlines()]
    rows.append({**rows[1], "actor": 0, "action": "bot_action"})
    rows.append({key: value for key, value in rows[1].items() if key != "actor"})
    path.write_text("\n".join(map(json.dumps, rows)))
    report = client.post("/analyze/test_session").json()
    assert len(report["decision_points"]) == 1
    assert len(report["unattributed_decisions"]) == 1
    assert "bot_action" not in json.dumps(report)


def test_went_well_cites_observed_human_success_without_jev(client):
    path = client.app.state.settings.data_dir / "recordings/test_session.jsonl"
    with path.open("a") as output:
        output.write(json.dumps({"t": "event", "session_id": "test_session", "round": 1,
                                 "frame": 10, "kind": "throw_break", "actor": 1, "target": 0}) + "\n")
    report = client.post("/analyze/test_session").json()
    assert len(report["went_well"]) == 1
    assert "round 1, frame 10" in report["went_well"][0]
    assert "line 4" in report["went_well"][0]
    assert report["decision_points"][0]["options"] == []


def test_jev_batches_and_retains_partial_success(client):
    from replay.scoring import JevScorer

    calls = []

    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if len(calls) == 2:
            raise httpx.ReadTimeout("private-provider-details")
        return httpx.Response(200, json={"answers": {key: {
            "type": "choice", "choice": "guard", "probabilities": {"guard": 0.7, "step": 0.3}}
            for key in payload["questions"]}})

    path = client.app.state.settings.data_dir / "recordings/test_session.jsonl"
    rows = [json.loads(row) for row in path.read_text().splitlines()]
    rows.extend([rows[1]] * 12)
    path.write_text("\n".join(map(json.dumps, rows)))
    client.app.state.reports.option_generator = generate
    client.app.state.reports.scorer = JevScorer("test", transport=httpx.MockTransport(respond))
    report = client.post("/analyze/test_session").json()
    assert report["scoring_summary"] == {"scored": 12, "unavailable": 1}
    assert len(calls) == 2
    assert "private-provider" not in json.dumps(report)


def test_neutral_sample_preserves_all_59_recorded_human_actions(tmp_path):
    import asyncio

    from replay.reports import ReportService, default_options
    from replay.scoring import JevScorer

    source = ROOT / "data/samples/versus_djin_vs_kaz_l3_neutral/versus_djin_vs_kaz_l3_neutral.jsonl"
    if not source.exists():
        pytest.skip("Neutral sample has not been extracted")
    rows = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
    session = rows[0]["session_id"]
    folder = tmp_path / "recordings"
    folder.mkdir()
    import shutil

    shutil.copyfile(source, folder / f"{session}.jsonl")
    service = ReportService(tmp_path, JevScorer(""), default_options)
    report = asyncio.run(service.analyze(session))
    expected = [(row["round"], row["frame"], row["action"]) for row in rows
                if row.get("kind") == "decision_point" and row.get("actor") == 0]
    actual = [(point["round"], point["frame"], point["actual"]) for point in report["decision_points"]]
    assert actual == expected and len(actual) == 59
    assert report["scoring_summary"] == {"scored": 0, "unavailable": 59}
    assert all(not point["options"] for point in report["decision_points"])
    assert report["source"]["tactical_sources"] == {"default": 220, "reflex": 152}
    Draft202012Validator(SCHEMA).validate(report)
