import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import httpx

from game import api, bot
from game.coach import FALLBACK, Outlet, replay_url, tip_from
from game.hotloop import Hooks, run_session
from game.tests.test_hotloop import FakeReader
from game.tests.test_state import idle

SUMMARY = {"t": "round_summary", "session_id": "s1", "round": 2, "frame": 900, "winner": 1, "human_slot": 0,
           "human_damage_taken": 120, "bot_damage_taken": 40, "top_habits": [], "biggest_moments": []}


def outlet_with(handler, log=None):
    seen = []
    out = Outlet(seen.append, url="http://replay.test", transport=httpx.MockTransport(handler), log=log or (lambda s: None))
    return out, seen


def coach_records(seen):
    return [r for r in seen if r.get("t") == "coach"]


class StateThrottleTest(unittest.TestCase):
    def test_states_go_out_every_second_frame_and_on_a_new_round(self):
        out, seen = outlet_with(lambda r: httpx.Response(200))
        for rnd, frame in [(1, 0), (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (2, 0), (2, 1), (2, 2)]:
            out.state({"t": "state", "round": rnd, "frame": frame})
        self.assertEqual([(r["round"], r["frame"]) for r in seen], [(1, 0), (1, 2), (1, 4), (2, 0), (2, 2)])

    def test_a_skipped_frame_still_publishes_and_a_counter_reset_restarts(self):
        out, seen = outlet_with(lambda r: httpx.Response(200))
        for frame in (10, 13, 14, 5, 6):
            out.state({"t": "state", "round": 1, "frame": frame})
        self.assertEqual([r["frame"] for r in seen], [10, 13, 5])

    def test_a_failing_publish_never_reaches_the_caller(self):
        def boom(rec):
            raise RuntimeError("down")
        out = Outlet(boom, url="http://replay.test", transport=httpx.MockTransport(lambda r: httpx.Response(500)), log=lambda s: None)
        out.state({"t": "state", "round": 1, "frame": 0})
        out.records([{"t": "event", "kind": "hit"}, dict(SUMMARY)])
        self.assertTrue(out.close(5))


class CoachTest(unittest.TestCase):
    def test_round_summary_is_posted_and_the_reply_published(self):
        posted = []

        def handler(request):
            posted.append((str(request.url), json.loads(request.content)))
            return httpx.Response(200, json={"text": "Block low after his df+1.", "severity": "warn"})

        out, seen = outlet_with(handler)
        out.records([{"t": "event", "kind": "round_end"}, dict(SUMMARY)])
        self.assertTrue(out.close(5))
        self.assertEqual(posted, [("http://replay.test/coach/round", SUMMARY)])
        self.assertEqual(coach_records(seen), [{"t": "coach", "session_id": "s1", "round": 2, "text": "Block low after his df+1.", "severity": "warn"}])
        self.assertEqual([r["t"] for r in seen], ["event", "round_summary", "coach"])

    def test_unknown_severity_becomes_info(self):
        out, seen = outlet_with(lambda r: httpx.Response(200, json={"text": "Nice.", "severity": "loud"}))
        out.records([dict(SUMMARY)])
        out.close(5)
        self.assertEqual(coach_records(seen)[0]["severity"], "info")

    def test_failures_fall_back_to_the_generic_tip(self):
        def refused(request):
            raise httpx.ConnectError("refused")

        def slow(request):
            raise httpx.ReadTimeout("slow")

        cases = [lambda r: httpx.Response(500), lambda r: httpx.Response(422, json={"detail": []}),
                 lambda r: httpx.Response(200, json={"severity": "info"}), lambda r: httpx.Response(200, text="not json"), refused, slow]
        for handler in cases:
            logs = []
            out, seen = outlet_with(handler, logs.append)
            out.records([dict(SUMMARY)])
            self.assertTrue(out.close(5))
            self.assertEqual(coach_records(seen), [{"t": "coach", "session_id": "s1", "round": 2, "text": FALLBACK, "severity": "info"}])
            self.assertIn("fallback", logs[0])

    def test_timeout_is_eight_seconds(self):
        out = Outlet(lambda r: None)
        self.assertEqual(out.timeout, 8.0)

    def test_replay_url_comes_from_the_environment(self):
        with mock.patch.dict(os.environ, {"KUMITE_REPLAY_URL": "http://10.0.0.5:8766/"}):
            self.assertEqual(replay_url(), "http://10.0.0.5:8766")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(replay_url(), "http://127.0.0.1:8766")

    def test_tip_from_rejects_empty_text(self):
        self.assertIsNone(tip_from({"text": "  ", "severity": "info"}))
        self.assertIsNone(tip_from(["text"]))
        self.assertEqual(tip_from({"text": " Go. ", "severity": "praise"}), ("Go.", "praise"))


class SummaryHooks(Hooks):
    def finish(self, state, events):
        return [dict(SUMMARY, session_id=state["session_id"], round=state["round"])]


class HotLoopTest(unittest.TestCase):
    def test_the_hot_loop_publishes_states_events_and_the_final_tip(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"DATA_DIR": tmp}):
            out, seen = outlet_with(lambda r: httpx.Response(200, json={"text": "Tip.", "severity": "info"}))
            args = SimpleNamespace(bot="kazuya", player="pub", difficulty=3, mode="practice", stage=None, rounds_to_win=None)
            run_session(FakeReader([(f, [idle(0, f), idle(1, f)]) for f in range(1, 31)]), args, SummaryHooks(), out)
            kinds = [r["t"] for r in seen]
            self.assertEqual(kinds.count("state"), 15)
            self.assertEqual([r["kind"] for r in seen if r["t"] == "event"], ["round_start", "round_end"])
            self.assertEqual(kinds[-2:], ["round_summary", "coach"])
            recording = next(Path(tmp, "recordings").glob("*.jsonl")).read_text(encoding="utf-8")
            self.assertNotIn('"t":"coach"', recording)


class StartTest(unittest.TestCase):
    def test_start_returns_none_when_the_port_is_taken(self):
        with socket.socket() as busy:
            busy.bind(("127.0.0.1", 0))
            busy.listen(1)
            self.assertIsNone(api.start(port=busy.getsockname()[1], wait=5))

    def test_start_serves_health(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        started = api.start(port=port)
        self.assertIsNotNone(started)
        server, thread = started
        try:
            self.assertTrue(httpx.get(f"http://127.0.0.1:{port}/health", timeout=5).json()["ok"])
        finally:
            server.should_exit = True
            thread.join(5)


class BotArgsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def args(self, *extra):
        return bot.parse_args(["--bot", "kazuya", *extra], root=self.tmp.name)

    def test_player_flag_wins(self):
        a = self.args("--player", "eric", "--demo")
        self.assertEqual((a.player, a.demo), ("eric", True))

    def test_demo_defaults_to_guest(self):
        self.assertEqual(self.args("--demo").player, "guest")

    def test_config_player_is_the_default(self):
        self.assertEqual(self.args().player, "sahil")
        Path(self.tmp.name, "config.json").write_text(json.dumps({"player": "chloe"}), encoding="utf-8")
        a = self.args()
        self.assertEqual((a.player, a.demo, a.no_api), ("chloe", False, False))


if __name__ == "__main__":
    unittest.main()
