import asyncio
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from game import api

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "data" / "samples" / "live_learning"
SID = "2026-10-18T05-14-03_sahil_djin_vs_kaz"


def schema(name):
    return Draft202012Validator(json.loads((ROOT / "contracts" / f"{name}.schema.json").read_text(encoding="utf-8")), format_checker=FormatChecker())


SESSION_V = schema("session")
PROFILE_V = schema("profile")
CONFIG_V = schema("config")


def state(frame, round_=1):
    return {"t": "state", "session_id": SID, "round": round_, "frame": frame}


def event(frame, kind="block", round_=1):
    return {"t": "event", "session_id": SID, "round": round_, "frame": frame, "kind": kind}


def publish_later(records, hub=None, delay=0.05):
    def run():
        time.sleep(delay)
        for record in records:
            (hub.publish if hub else api.publish)(record)

    thread = threading.Thread(target=run)
    thread.start()
    return thread


class ApiReadTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DATA_DIR": str(LIVE)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(api.create_app())
        self.assertFalse((LIVE / "config.json").exists())

    def test_health(self):
        body = self.client.get("/health").json()
        self.assertEqual(set(body), {"ok", "service", "version"})
        self.assertEqual((body["ok"], body["service"]), (True, "brain"))
        self.assertTrue(body["version"])

    def test_cors_open(self):
        response = self.client.options("/config", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(response.headers["access-control-allow-origin"], ("*", "http://localhost:5173"))

    def test_sessions(self):
        sessions = self.client.get("/sessions").json()
        self.assertEqual([s["session_id"] for s in sessions], [SID])
        self.assertEqual(list(SESSION_V.iter_errors(sessions[0])), [])
        self.assertEqual(sessions[0]["result"], "loss 1-3")

    def test_session_by_id(self):
        meta = self.client.get(f"/sessions/{SID}").json()
        self.assertEqual(meta, json.loads((LIVE / "sessions" / f"{SID}.json").read_text(encoding="utf-8")))
        self.assertEqual(self.client.get("/sessions/nope").status_code, 404)
        self.assertEqual(self.client.get("/sessions/..%5C..%5Cconfig").status_code, 404)
        self.assertEqual(self.client.get("/sessions/.hidden").status_code, 404)

    def test_recording(self):
        response = self.client.get(f"/sessions/{SID}/recording")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("application/x-ndjson"))
        expected = (LIVE / "recordings" / f"{SID}.jsonl").read_bytes()
        self.assertEqual(int(response.headers["content-length"]), len(expected))
        self.assertEqual(response.content, expected)
        self.assertEqual(self.client.get("/sessions/nope/recording").status_code, 404)

    def test_profiles(self):
        profiles = self.client.get("/profiles/sahil").json()
        self.assertEqual([p["character"] for p in profiles], ["devil_jin"])
        self.assertEqual(list(PROFILE_V.iter_errors(profiles[0])), [])
        self.assertEqual(self.client.get("/profiles/nobody").json(), [])

    def test_default_config(self):
        config = self.client.get("/config").json()
        self.assertEqual(list(CONFIG_V.iter_errors(config)), [])
        self.assertEqual(config, api.DEFAULT_CONFIG)


class ApiDataDirTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        patcher = mock.patch.dict(os.environ, {"DATA_DIR": str(self.root)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(api.create_app())

    def test_empty_data_dir(self):
        self.assertEqual(self.client.get("/sessions").json(), [])
        self.assertEqual(self.client.get("/profiles/sahil").json(), [])
        self.assertEqual(self.client.get("/config").json(), api.DEFAULT_CONFIG)

    def test_sessions_newest_first_and_bad_files_skipped(self):
        (self.root / "sessions").mkdir()
        meta = json.loads((LIVE / "sessions" / f"{SID}.json").read_text(encoding="utf-8"))
        newer = dict(meta, session_id="2026-10-19T01-00-00_sahil_djin_vs_kaz", started_at="2026-10-19T01:00:00Z")
        for m in (meta, newer):
            (self.root / "sessions" / f"{m['session_id']}.json").write_text(json.dumps(m), encoding="utf-8")
        (self.root / "sessions" / "broken.json").write_text("{", encoding="utf-8")
        ids = [s["session_id"] for s in self.client.get("/sessions").json()]
        self.assertEqual(ids, [newer["session_id"], SID])

    def test_post_config_merges_and_persists(self):
        merged = self.client.post("/config", json={"difficulty": 4, "knobs": {"exploit_weight": 0.5}}).json()
        self.assertEqual(list(CONFIG_V.iter_errors(merged)), [])
        self.assertEqual((merged["difficulty"], merged["knobs"], merged["player"]), (4, {"exploit_weight": 0.5}, "sahil"))
        merged = self.client.post("/config", json={"knobs": {"reaction_delay_frames": 10}, "player": "chloe"}).json()
        self.assertEqual(merged["knobs"], {"exploit_weight": 0.5, "reaction_delay_frames": 10})
        self.assertEqual(merged["difficulty"], 4)
        self.assertEqual(json.loads((self.root / "config.json").read_text(encoding="utf-8")), merged)
        self.assertEqual(TestClient(api.create_app()).get("/config").json(), merged)
        cleared = self.client.post("/config", json={"knobs": {"exploit_weight": None}}).json()
        self.assertEqual(cleared["knobs"], {"reaction_delay_frames": 10})

    def test_post_config_rejects_invalid(self):
        before = self.client.get("/config").json()
        for body in ({"difficulty": 9}, {"knobs": {"exploit_weight": 2}}, {"bot_character": "heihachi"}, {"knobs": {"combo_set": "long"}}, {"player": None}):
            response = self.client.post("/config", json=body)
            self.assertEqual(response.status_code, 422, body)
            self.assertTrue(response.json()["errors"], body)
        self.assertEqual(self.client.post("/config", content="{").status_code, 422)
        self.assertEqual(self.client.post("/config", json=[1, 2]).status_code, 422)
        self.assertEqual(self.client.get("/config").json(), before)
        self.assertFalse((self.root / "config.json").exists())

    def test_corrupt_config_file_falls_back(self):
        (self.root / "config.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(self.client.get("/config").json(), api.DEFAULT_CONFIG)
        (self.root / "config.json").write_text(json.dumps({"difficulty": 99}), encoding="utf-8")
        self.assertEqual(self.client.get("/config").json(), api.DEFAULT_CONFIG)

    def test_recording_growing_file_sends_snapshot(self):
        (self.root / "recordings").mkdir()
        path = self.root / "recordings" / f"{SID}.jsonl"
        path.write_text(json.dumps(state(1)) + "\n", encoding="utf-8")
        response = self.client.get(f"/sessions/{SID}/recording")
        self.assertEqual(response.content, path.read_bytes())


class WebSocketTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DATA_DIR": str(LIVE)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(api.create_app())

    def test_state_stream_gets_states_and_events(self):
        with self.client.websocket_connect("/ws/state") as ws:
            thread = publish_later([state(1), event(1), {"t": "tactical", "frame": 1}, {"t": "coach", "text": "x"}, state(2)])
            got = [ws.receive_json() for _ in range(3)]
            thread.join()
        self.assertEqual([(r["t"], r["frame"]) for r in got], [("state", 1), ("event", 1), ("state", 2)])

    def test_gamestate_alias_routes_to_state(self):
        with self.client.websocket_connect("/ws/state") as ws:
            publish_later([{"t": "gamestate", "frame": 7}]).join()
            self.assertEqual(ws.receive_json()["frame"], 7)

    def test_coach_stream(self):
        summary = {"t": "round_summary", "session_id": SID, "round": 1, "winner": 1}
        coach = {"t": "coach", "session_id": SID, "round": 1, "text": "Block the low.", "severity": "warn"}
        with self.client.websocket_connect("/ws/coach") as ws:
            publish_later([state(1), event(1), summary, coach]).join()
            self.assertEqual(ws.receive_json(), summary)
            self.assertEqual(ws.receive_json(), coach)

    def test_fan_out_to_every_client(self):
        with self.client.websocket_connect("/ws/state") as a, self.client.websocket_connect("/ws/state") as b:
            publish_later([event(5)]).join()
            self.assertEqual(a.receive_json()["frame"], 5)
            self.assertEqual(b.receive_json()["frame"], 5)

    def test_disconnect_unsubscribes(self):
        with self.client.websocket_connect("/ws/state"):
            self.assertEqual(len(api.HUB.subscribers["state"]), 1)
        for _ in range(100):
            if not api.HUB.subscribers["state"]:
                break
            time.sleep(0.01)
        self.assertEqual(api.HUB.subscribers["state"], ())
        api.publish(state(1))

    def test_events_survive_state_flood(self):
        hub = api.Hub(state_backlog=8, max_backlog=10000)
        client = TestClient(api.create_app(hub=hub))
        records = []
        for frame in range(600):
            records.append(state(frame))
            if frame % 20 == 0:
                records.append(event(frame))
        with client.websocket_connect("/ws/state") as ws:
            thread = publish_later(records, hub=hub)
            thread.join()
            publish_later([event(9999, kind="round_end")], hub=hub).join()
            got = []
            while not got or got[-1].get("kind") != "round_end":
                got.append(ws.receive_json())
        events = [r["frame"] for r in got if r["t"] == "event"]
        self.assertEqual(events, list(range(0, 600, 20)) + [9999])
        frames = [r["frame"] for r in got if r["t"] == "state"]
        self.assertEqual(frames, sorted(frames))


class HubTest(unittest.TestCase):
    def test_publish_without_subscribers_or_bad_input_never_raises(self):
        hub = api.Hub()
        for record in (state(1), {"t": "event", "x": object()}, None, 5, "text", {"no": "t"}):
            self.assertIsNone(hub.publish(record))

    def test_unserializable_record_is_dropped(self):
        async def run():
            hub = api.Hub()
            sub = hub.subscribe("state")
            hub.publish({"t": "event", "x": object()})
            hub.publish(event(1))
            return list(sub.queue)

        self.assertEqual([json.loads(t)["frame"] for t in asyncio.run(run())], [1])

    def test_backlog_drops_states_keeps_events(self):
        async def run():
            hub = api.Hub(state_backlog=4, max_backlog=100)
            sub = hub.subscribe("state")
            for frame in range(10):
                hub.publish(state(frame))
            hub.publish(event(10))
            hub.publish(event(11))
            return sub

        sub = asyncio.run(run())
        texts = [json.loads(t) for t in sub.queue]
        self.assertEqual([(r["t"], r["frame"]) for r in texts], [("state", 0), ("state", 1), ("state", 2), ("state", 3), ("event", 10), ("event", 11)])
        self.assertEqual(sub.dropped, 6)
        self.assertFalse(sub.overflow)

    def test_slow_client_overflows_instead_of_growing(self):
        async def run():
            hub = api.Hub(state_backlog=4, max_backlog=8)
            sub = hub.subscribe("coach")
            for i in range(20):
                hub.publish({"t": "coach", "round": i})
            return sub

        sub = asyncio.run(run())
        self.assertTrue(sub.overflow)
        self.assertEqual(len(sub.queue), 0)

    def test_publish_from_another_thread_is_fast(self):
        async def run():
            hub = api.Hub()
            sub = hub.subscribe("state")
            started = time.perf_counter()
            thread = threading.Thread(target=lambda: [hub.publish(state(f)) for f in range(2000)])
            thread.start()
            await asyncio.get_running_loop().run_in_executor(None, thread.join)
            elapsed = time.perf_counter() - started
            batch = await asyncio.wait_for(sub.next_batch(), 1)
            return elapsed, batch

        elapsed, batch = asyncio.run(run())
        self.assertLess(elapsed, 2.0)
        self.assertEqual(len(batch), api.STATE_BACKLOG)

    def test_merge(self):
        base = {"a": 1, "k": {"x": 1, "y": 2}}
        self.assertEqual(api.merge(base, {"k": {"y": 3, "z": 4}, "b": 2}), {"a": 1, "b": 2, "k": {"x": 1, "y": 3, "z": 4}})
        self.assertEqual(api.merge(base, {"k": {"x": None}}), {"a": 1, "k": {"y": 2}})
        self.assertEqual(base, {"a": 1, "k": {"x": 1, "y": 2}})


if __name__ == "__main__":
    unittest.main()
