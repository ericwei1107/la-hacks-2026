import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from replay.coach import Composition, RoundCoach

ROOT = Path(__file__).resolve().parents[2]
STATE = json.loads((ROOT / "contracts/examples/gamestate.json").read_text())
SUMMARY = json.loads((ROOT / "contracts/examples/round_summary.json").read_text())
SESSION = "2026-10-18T15-00-00_test_djin_vs_kaz"
SLIDING_LOW = 0x6C6
DEMON_GOD_FIST = 0x698
DOUBLE_HIGH_SWEEP = 0x814
ABOLISHING_FIST = 0x6AF


def state(frame, round_number=1, health=(190, 190), situation="defense"):
    row = copy.deepcopy(STATE)
    row.update(session_id=SESSION, round=round_number, frame=frame, human_slot=0)
    row["players"][0]["health"], row["players"][1]["health"] = health
    row["derived"]["situation"] = situation
    return row


def event(frame, kind, round_number=1, **fields):
    return {"t": "event", "session_id": SESSION, "round": round_number, "frame": frame, "kind": kind, **fields}


def low_hit(frame, round_number, damage=14):
    return [state(frame, round_number),
            event(frame, "hit", round_number, actor=1, target=0, move_id=SLIDING_LOW, hit_level="low", frame_advantage=-1, damage=damage),
            event(frame, "decision_point", round_number, actor=0, target=1, situation="low_defense", action="hit", move_id=SLIDING_LOW,
                  detail={"start_frame": frame, "correct": False, "damage": damage, "event": "hit"})]


def throw(frame, round_number):
    return [state(frame, round_number),
            event(frame, "throw", round_number, actor=1, target=0, move_id=DOUBLE_HIGH_SWEEP, hit_level="throw", detail={"break": "press_2"}),
            state(frame + 30, round_number, health=(155, 190)),
            event(frame + 30, "decision_point", round_number, actor=0, target=1, situation="throw_break", action="none", move_id=DOUBLE_HIGH_SWEEP,
                  detail={"start_frame": frame, "correct": False, "code": "press_2"})]


def unpunished_block(frame, round_number):
    return [state(frame, round_number),
            event(frame, "block", round_number, actor=1, target=0, move_id=DEMON_GOD_FIST, hit_level="mid", frame_advantage=-18, damage=0)]


def summary(round_number, damage, habits):
    row = copy.deepcopy(SUMMARY)
    row.update(session_id=SESSION, round=round_number, frame=3000, human_damage_taken=damage, bot_damage_taken=40,
               top_habits=habits, biggest_moments=[], exploited=[], newly_fixed=[], regressed=[])
    return row


def write_recording(folder, rounds, truncated=False):
    rows = []
    for round_number, pieces in rounds.items():
        rows.append(state(0, round_number, situation="neutral"))
        rows.append(event(0, "round_start", round_number))
        for piece in pieces:
            rows.extend(piece)
    text = "\n".join(json.dumps(row) for row in rows) + "\n"
    if truncated:
        text += json.dumps(state(9999, max(rounds)))[:40]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{SESSION}.jsonl").write_text(text, encoding="utf-8")


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("KUMITE_COACH_MODE", "local")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from replay.main import create_app

    with TestClient(create_app()) as instance:
        yield instance


LOW_HABIT = {"situation": "low_defense", "action": "hit", "p": 0.8, "n": 4, "mastery": 0.2, "fixed": False}
THROW_HABIT = {"situation": "throw_break", "action": "none", "p": 1.0, "n": 3, "mastery": 0.1, "fixed": False}


def round_one(folder, truncated=False):
    pieces = [low_hit(100, 1), low_hit(200, 1), low_hit(300, 1), low_hit(400, 1),
              throw(500, 1), throw(700, 1), throw(900, 1), unpunished_block(1100, 1), unpunished_block(1300, 1)]
    write_recording(folder, {1: pieces}, truncated=truncated)


def test_throws_outrank_lows_when_they_cost_more(client, tmp_path):
    round_one(tmp_path / "recordings")
    result = client.post("/coach/round", json=summary(1, 161, [THROW_HABIT, LOW_HABIT])).json()
    assert result["severity"] == "warn"
    assert "Double High Sweep" in result["text"] and "1+3" in result["text"]
    assert "press 2" in result["text"]
    last = client.app.state.coach.last
    assert last["topic"] == "throw_break"
    topics = [candidate["topic"] for candidate in last["candidates"]]
    assert "low_defense" in topics and "missed_punish" in topics and "neutral" not in topics
    missed = next(candidate for candidate in last["candidates"] if candidate["topic"] == "missed_punish")
    assert "Demon God Fist" in missed["text"] and "b+1+3" in missed["text"] and "-18" in missed["text"]
    assert 0 < len(result["text"].split()) <= 30


def test_previous_topic_is_not_repeated_unless_it_cost_most_again(client, tmp_path):
    folder = tmp_path / "recordings"
    pieces = {1: [throw(500, 1), throw(700, 1), throw(900, 1), low_hit(100, 1), low_hit(200, 1), low_hit(300, 1)],
              2: [throw(500, 2), low_hit(100, 2, 30), low_hit(200, 2, 30), low_hit(300, 2, 30), low_hit(400, 2, 30)],
              3: [throw(500, 3), low_hit(100, 3, 30), low_hit(200, 3, 30), low_hit(300, 3, 30), low_hit(400, 3, 30)]}
    write_recording(folder, pieces)
    first = client.post("/coach/round", json=summary(1, 147, [THROW_HABIT, LOW_HABIT])).json()
    assert client.app.state.coach.last["topic"] == "throw_break"
    second = client.post("/coach/round", json=summary(2, 155, [THROW_HABIT, LOW_HABIT])).json()
    assert client.app.state.coach.last["topic"] == "low_defense"
    assert "Sliding Low Kick" in second["text"] and "db+3" in second["text"]
    third = client.post("/coach/round", json=summary(3, 155, [THROW_HABIT, LOW_HABIT])).json()
    assert client.app.state.coach.last["topic"] == "low_defense"
    assert first["text"] != second["text"] and second["text"] == third["text"]


def test_truncated_last_line_is_tolerated(client, tmp_path):
    round_one(tmp_path / "recordings", truncated=True)
    response = client.post("/coach/round", json=summary(1, 161, [THROW_HABIT, LOW_HABIT]))
    assert response.status_code == 200
    assert client.app.state.coach.last["topic"] == "throw_break"


def test_flushed_rounds_are_read_incrementally(client, tmp_path):
    folder = tmp_path / "recordings"
    write_recording(folder, {1: [low_hit(100, 1), low_hit(200, 1), low_hit(300, 1), low_hit(400, 1)]})
    client.post("/coach/round", json=summary(1, 56, [LOW_HABIT]))
    assert client.app.state.coach.last["topic"] == "low_defense"
    with (folder / f"{SESSION}.jsonl").open("a", encoding="utf-8") as output:
        for piece in [state(0, 2, situation="neutral")], throw(500, 2), throw(700, 2), throw(900, 2):
            for row in piece:
                output.write(json.dumps(row) + "\n")
    client.post("/coach/round", json=summary(2, 105, [THROW_HABIT, LOW_HABIT]))
    assert client.app.state.coach.last["topic"] == "throw_break"


def test_composed_tip_with_grounded_facts_is_spoken(client, tmp_path):
    round_one(tmp_path / "recordings")

    async def provider(summary, advice):
        return Composition(text="Kazuya's Double High Sweep grabbed you 3 times. Press 2 the moment the grab starts.",
                           moves=["Double High Sweep", "2"])

    client.app.state.coach = RoundCoach(provider=provider, data_dir=tmp_path)
    result = client.post("/coach/round", json=summary(1, 161, [THROW_HABIT, LOW_HABIT])).json()
    assert result["text"].startswith("Kazuya's Double High Sweep grabbed you 3 times.")
    assert result["severity"] == "warn"
    assert client.app.state.coach.last["source"] == "provider_composed"


@pytest.mark.parametrize("text,moves", [
    ("Double High Sweep grabbed you 3 times. Break it with 1+2 as the grab starts.", ["Double High Sweep", "1+2"]),
    ("Double High Sweep grabbed you 5 times. Press 2 as the grab starts.", ["Double High Sweep", "2"]),
    ("Double High Sweep grabbed you 3 times. Duck it and answer with Electric Wind God Fist.", ["Double High Sweep"]),
    ("Double High Sweep grabbed you 3 times. Punish with f,n,d,df+2 every time.", ["Double High Sweep"]),
])
def test_hallucinated_composition_falls_back_to_template(client, tmp_path, text, moves):
    round_one(tmp_path / "recordings")

    async def provider(summary, advice):
        return Composition(text=text, moves=moves)

    client.app.state.coach = RoundCoach(provider=provider, data_dir=tmp_path)
    result = client.post("/coach/round", json=summary(1, 161, [THROW_HABIT, LOW_HABIT])).json()
    assert result["text"] == client.app.state.coach.last["candidates"][0]["text"]
    assert client.app.state.coach.last["source"] == "local"


def test_missing_recording_keeps_summary_only_advice(client):
    result = client.post("/coach/round", json=SUMMARY).json()
    assert result["severity"] == "warn"
    assert "low" in result["text"].lower()
    assert client.app.state.coach.last["topic"] is None


def test_mismatched_human_slot_ignores_the_recording(client, tmp_path):
    round_one(tmp_path / "recordings")
    row = summary(1, 161, [THROW_HABIT, LOW_HABIT])
    row["human_slot"] = 1
    client.post("/coach/round", json=row)
    assert client.app.state.coach.last["topic"] is None


def test_post_set_practice_lists_weaknesses_with_opponent_moves(client, tmp_path):
    round_one(tmp_path / "recordings")
    response = client.post("/coach/chat", json={"session_id": SESSION, "player": "sahil", "message": "What should I practice?", "history": []})
    assert response.status_code == 200
    reply = response.json()
    assert reply["text"].startswith("Start with throw breaks.")
    assert "3 of 3" in reply["text"] and "Double High Sweep" in reply["text"] and "press 2" in reply["text"]
    assert "Next, work on punishing." in reply["text"]
    assert "Demon God Fist" in reply["text"] and "b+1+3" in reply["text"] and "-18" in reply["text"]
    assert "Then work on low blocking." in reply["text"]
    assert "4 of 4" in reply["text"] and "Sliding Low Kick" in reply["text"] and "db+3" in reply["text"]
    assert "crouch-blocking" in reply["text"]
    assert {"round": 1, "frame": 530} in reply["citations"] and {"round": 1, "frame": 100} in reply["citations"]
    assert {"round": 1, "frame": 1100} in reply["citations"]


def test_real_sdk_parses_structured_composition_without_external_network(client, tmp_path, monkeypatch):
    import httpx
    from openai import AsyncOpenAI
    from replay import coach

    round_one(tmp_path / "recordings")
    composed = {"text": "Double High Sweep grabbed you 3 times this round. Press 2 the moment the grab starts.",
                "moves": ["Double High Sweep", "2"]}
    seen = []

    def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "resp_test", "object": "response", "created_at": 0,
            "model": "test-model", "status": "completed",
            "output": [{"id": "msg_test", "type": "message", "role": "assistant",
                        "status": "completed", "content": [{"type": "output_text",
                        "text": json.dumps(composed), "annotations": []}]}],
            "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
        })

    def make_client(**kwargs):
        return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))

    monkeypatch.setattr(coach, "AsyncOpenAI", make_client)
    client.app.state.coach = coach.RoundCoach(coach.OpenAIProvider("test-key", "test-model"), data_dir=tmp_path)
    response = client.post("/coach/round", json=summary(1, 161, [THROW_HABIT, LOW_HABIT]))
    assert response.status_code == 200
    assert response.json() == {"text": composed["text"], "severity": "warn"}
    assert seen[0]["text"]["format"]["strict"] is True
    assert set(seen[0]["text"]["format"]["schema"]["required"]) == {"text", "moves"}
    assert "Double High Sweep" in seen[0]["input"]


def chat(client, message):
    return client.post("/coach/chat", json={"session_id": SESSION, "player": "sahil", "message": message, "history": []}).json()


def test_report_habit_fix_cost_and_drills_come_from_the_evidence(client, tmp_path):
    from replay.scoring import JevScorer

    round_one(tmp_path / "recordings")
    client.app.state.reports.scorer = JevScorer("")
    report = client.post(f"/analyze/{SESSION}").json()
    habits = {habit["situation"]: habit for habit in report["habits"]}
    assert "Sliding Low Kick (db+3)" in habits["low_defense"]["min_change"] and "d+2" in habits["low_defense"]["min_change"]
    assert "Double High Sweep (1+3)" in habits["throw_break"]["min_change"] and "press 2" in habits["throw_break"]["min_change"]
    costs = {(point["situation"], point["frame"]): point.get("cost") for point in report["decision_points"]}
    assert costs[("low_defense", 100)] == 14 and costs[("throw_break", 530)] == 35
    assert all(point["good"] is False for point in report["decision_points"])
    assert any("Demon God Fist" in drill and "b+1+3" in drill for drill in report["drills"])
    assert all("In Practice" in drill for drill in report["drills"])
    assert client.get(f"/reports/{SESSION}").json() == report


def test_chat_default_answer_speaks_like_a_coach(client, tmp_path):
    round_one(tmp_path / "recordings")
    reply = chat(client, "How am I doing against the lows?")
    assert "you got hit by the low 4 of 4 times" in reply["text"]
    assert "Sliding Low Kick (db+3)" in reply["text"] and "d+2" in reply["text"]
    assert "recorded response" not in reply["text"] and "does not establish" not in reply["text"]


def test_beat_question_and_combos_use_character_data(client, tmp_path):
    round_one(tmp_path / "recordings")
    reply = chat(client, "What combos should I use and how do I beat Kazuya?")
    assert reply["text"].startswith("Devil Jin's reliable combos")
    assert "After Wind God Fist (f,n,d,df+2)" in reply["text"] and "for 55" in reply["text"]
    assert "Start with throw breaks" in reply["text"] and "Double High Sweep" in reply["text"]
    reply = chat(client, "How do I beat Kazuya?")
    assert reply["text"].startswith("Start with throw breaks.")


def test_progress_question_tells_the_round_by_round_story(client, tmp_path):
    pieces = {1: [low_hit(100, 1), low_hit(200, 1), low_hit(300, 1), throw(500, 1)],
              2: [low_hit(100, 2), throw(500, 2), throw(700, 2)]}
    write_recording(tmp_path / "recordings", pieces)
    reply = chat(client, "Have I been improving per round?")
    assert "Kazuya's lows hit you 3, 1 times round by round, trending the right way" in reply["text"]
    assert "Throws landed on you 1, 2 times round by round, trending up, so fix that first" in reply["text"]
    assert "unavailable" in reply["text"].lower() or "missing" in reply["text"].lower()


def test_composed_chat_reply_is_spoken_only_when_grounded(client, tmp_path):
    from replay.chat import AnswerPlan

    round_one(tmp_path / "recordings")
    grounded = ("Two things cost you this set. Kazuya's Sliding Low Kick, db+3, caught you 4 of 4 times, so hold down-back "
                "and answer with d+2. And Double High Sweep grabbed you 3 of 3 times: press 2 as the grab starts.")
    hallucinated = ("Kazuya's Sliding Low Kick caught you 4 of 4 times. Duck the Hellsweep and launch with "
                    "Electric Wind God Fist for 70 damage.")
    outcomes = {}
    for label, text in (("grounded", grounded), ("hallucinated", hallucinated)):
        async def provider(request, tools, initial, text=text):
            return AnswerPlan(fact_ids=[fact["id"] for fact in initial[:3]], text=text, moves=[])

        client.app.state.chat.provider = provider
        outcomes[label] = chat(client, "What should I practice?")
    assert outcomes["grounded"]["text"] == grounded
    assert outcomes["grounded"]["citations"]
    assert outcomes["hallucinated"]["text"].startswith("Start with throw breaks.")
    assert "Hellsweep" not in outcomes["hallucinated"]["text"]
