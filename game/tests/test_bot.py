import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient

from game import api, bot
from game.hotloop import INTERRUPTED, MATCH_OVER, run_session, wait_for_match
from game.tests.test_hotloop import FakeReader, SpyHooks
from game.tests.test_state import idle


class NoPacer:
    def wait(self):
        pass


class ScriptedReader:
    def __init__(self, snaps):
        self.snaps = iter(snaps)

    def snapshot(self):
        try:
            item = next(self.snaps)
        except StopIteration:
            raise KeyboardInterrupt
        if item is None:
            return None
        frame, players = item
        return SimpleNamespace(players=players, human_slot=0, round_frame=frame)


def pair(frame, h0=190, h1=190, free=1):
    return (frame, [idle(0, frame, health=h0, free_movement=free), idle(1, frame, health=h1, free_movement=free)])


class ConfigRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def args(self, *extra):
        return bot.parse_args(["--bot", "kazuya", *extra], root=self.root)

    def stored(self):
        return json.loads((self.root / "config.json").read_text(encoding="utf-8"))

    def test_cli_flags_are_written_to_config_and_read_back(self):
        a = self.args("--difficulty", "4", "--player", "eve")
        cfg, errors = bot.apply_cli(a, self.root)
        self.assertEqual(errors, [])
        self.assertEqual((self.stored()["difficulty"], self.stored()["player"]), (4, "eve"))
        cfg, difficulty, player, fresh = bot.settings(a, self.root)
        self.assertEqual((difficulty.level, player, fresh), (4, "eve", False))

    def test_no_flags_leave_config_alone_and_follow_it(self):
        a = self.args()
        self.assertIsNone(a.difficulty)
        self.assertFalse(a.loop)
        cfg, errors = bot.apply_cli(a, self.root)
        self.assertFalse((self.root / "config.json").exists())
        cfg, difficulty, player, fresh = bot.settings(a, self.root)
        self.assertEqual((difficulty.level, player, fresh), (api.DEFAULT_CONFIG["difficulty"], "sahil", False))

    def test_post_config_between_matches_changes_the_next_session(self):
        a = self.args("--difficulty", "3", "--loop")
        bot.apply_cli(a, self.root)
        self.assertTrue(a.loop)
        self.assertEqual(bot.settings(a, self.root)[1].level, 3)
        client = TestClient(api.create_app(self.root))
        reply = client.post("/config", json={"difficulty": 5, "knobs": {"reaction_delay_frames": 7}})
        self.assertEqual(reply.status_code, 200)
        cfg, difficulty, player, fresh = bot.settings(a, self.root)
        self.assertEqual((difficulty.level, difficulty.reaction_delay_frames, difficulty.punish_accuracy), (5, 7, 1.0))
        self.assertIn("difficulty 5 with knobs reaction_delay_frames=7", bot.describe(cfg, difficulty, player, fresh, self.root))
        self.assertEqual(client.get("/config").json()["difficulty"], 5)

    def test_demo_from_config_or_flag_uses_a_fresh_guest_profile(self):
        a = self.args()
        self.assertEqual(bot.settings(a, self.root)[2:], ("sahil", False))
        api.update_config({"demo_mode": True}, self.root)
        self.assertEqual(bot.settings(a, self.root)[2:], ("guest", True))
        api.update_config({"demo_mode": False}, self.root)
        a = self.args("--demo")
        self.assertEqual(bot.settings(a, self.root)[2:], ("guest", True))
        a = self.args("--demo", "--player", "eric")
        bot.apply_cli(a, self.root)
        self.assertEqual(bot.settings(a, self.root)[2:], ("eric", True))

    def test_invalid_cli_patch_is_reported_not_written(self):
        a = self.args("--player", "eve")
        a.difficulty = 9
        cfg, errors = bot.apply_cli(a, self.root)
        self.assertTrue(errors)
        self.assertFalse((self.root / "config.json").exists())


class LoopTest(unittest.TestCase):
    def test_session_reports_match_over_at_the_post_match_reset(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"DATA_DIR": tmp}):
            args = SimpleNamespace(bot="kazuya", player="loop", difficulty=3, mode="versus", stage=None, rounds_to_win=1)
            frames = [pair(f) for f in range(1, 11)] + [pair(f, 190, 0) for f in range(11, 16)] + [pair(1, 190, 0), pair(2, 190, 0)]
            reason = run_session(FakeReader(frames), args, SpyHooks())
            self.assertEqual(reason, MATCH_OVER)
            meta = json.loads(next(Path(tmp, "sessions").glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual((meta["difficulty"], meta["player"], meta["rounds"][0]["winner"]), (3, "loop", 0))

    def test_session_reports_interrupted_on_ctrl_c(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"DATA_DIR": tmp}):
            args = SimpleNamespace(bot="kazuya", player="loop", difficulty=3, mode="versus", stage=None, rounds_to_win=3)
            self.assertEqual(run_session(FakeReader([pair(f) for f in range(1, 6)]), args, SpyHooks()), INTERRUPTED)

    def test_wait_for_match_skips_full_health_scenes_where_nobody_is_free(self):
        snaps = [pair(300, 0, 64), pair(301, 0, 64), pair(0, free=0), pair(1, free=0), pair(294, free=0), pair(0, free=0), pair(299, free=0),
                 pair(0, free=0), pair(1, free=0), pair(161, free=0), pair(162), pair(163)]
        logs = []
        snap = wait_for_match(ScriptedReader(snaps), NoPacer(), log=logs.append)
        self.assertEqual(snap.round_frame, 162)
        self.assertTrue(any("new match" in line for line in logs))

    def test_wait_for_match_after_menus_needs_full_health_and_free_players(self):
        snaps = [pair(300, 0, 64), None, None, pair(5, 100, 190), pair(6, 100, 190), pair(7, free=0), pair(8), pair(9)]
        polls = []
        snap = wait_for_match(ScriptedReader(snaps), NoPacer(), on_poll=lambda: polls.append(1), log=lambda line: None)
        self.assertEqual(snap.round_frame, 8)
        self.assertEqual(len(polls), 6)

    def test_wait_for_match_never_starts_without_a_new_scene(self):
        snaps = [pair(f, 0, 64) for f in range(300, 310)] + [pair(f) for f in range(310, 320)]
        with self.assertRaises(KeyboardInterrupt):
            wait_for_match(ScriptedReader(snaps), NoPacer(), log=lambda line: None)

    def test_wait_for_match_on_the_recorded_rematch_scenes(self):
        path = Path("data/recordings/2026-10-18T10-16-55_sahil_djin_vs_kaz.jsonl")
        if not path.exists():
            self.skipTest("live recording not on this machine")
        states = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        snaps = [(s["frame"], s["players"]) for s in states if s["t"] == "state" and s["round"] <= 3]
        snaps = [(400, snaps[0][1])] + snaps
        snap = wait_for_match(ScriptedReader(snaps), NoPacer(), log=lambda line: None)
        self.assertEqual(snap.round_frame, 162)
        self.assertEqual([hex(p["move_id"]) for p in snap.players], ["0x85a", "0x874"])


class LayaStartupTest(unittest.TestCase):
    def run_main(self, *extra, reasons=(MATCH_OVER, INTERRUPTED)):
        sessions = []
        script = iter(reasons)

        def session(reader, args, hooks, outlet):
            sessions.append((args.player, hooks.player, hooks.fresh))
            return next(script)

        pad = SimpleNamespace(check_kill=lambda: None, release_all=lambda: None)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"DATA_DIR": tmp}), \
                mock.patch.object(bot.laya, "start_background") as start, \
                mock.patch.object(bot, "Reader", return_value=SimpleNamespace(close=lambda: None)), \
                mock.patch.object(bot, "run_gate", return_value=True), \
                mock.patch.object(bot, "connect_pad", return_value=pad), \
                mock.patch.object(bot, "Pacer"), \
                mock.patch.object(bot, "run_session", side_effect=session), \
                mock.patch.object(bot, "wait_for_match") as wait:
            code = bot.main(["--bot", "kazuya", "--no-api", *extra])
        return code, start.call_count, wait.call_count, sessions

    def test_flag_defaults_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(bot.parse_args(["--bot", "kazuya"], root=Path(tmp)).no_laya)
            self.assertTrue(bot.parse_args(["--bot", "kazuya", "--no-laya"], root=Path(tmp)).no_laya)

    def test_loop_with_demo_loads_laya_once_and_keeps_playing_fresh_sessions(self):
        code, starts, waits, sessions = self.run_main("--loop", "--demo")
        self.assertEqual((code, starts, waits), (0, 1, 1))
        self.assertEqual(sessions, [("guest", "guest", True), ("guest", "guest", True)])

    def test_no_laya_skips_the_load(self):
        code, starts, waits, sessions = self.run_main("--loop", "--demo", "--no-laya")
        self.assertEqual((code, starts, waits, len(sessions)), (0, 0, 1, 2))

    def test_without_loop_one_session_and_one_load(self):
        code, starts, waits, sessions = self.run_main(reasons=(MATCH_OVER,))
        self.assertEqual((code, starts, waits, len(sessions)), (0, 1, 0, 1))

    def test_laya_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = bot.parse_args(["--bot", "kazuya"], root=Path(tmp))
            self.assertEqual((args.laya, args.laya_weight), (False, 0.3))
            args = bot.parse_args(["--bot", "kazuya", "--laya", "--laya-weight", "0.5"], root=Path(tmp))
            self.assertEqual((args.laya, args.laya_weight), (True, 0.5))
            with mock.patch("sys.stderr"):
                with self.assertRaises(SystemExit):
                    bot.parse_args(["--bot", "kazuya", "--laya", "--no-laya"], root=Path(tmp))
                with self.assertRaises(SystemExit):
                    bot.parse_args(["--bot", "kazuya", "--laya", "--laya-weight", "1.5"], root=Path(tmp))

    def test_laya_off_gives_the_hooks_no_oracle(self):
        hooks = []
        with mock.patch.object(bot, "BotHooks", side_effect=lambda *a, **k: hooks.append(k) or SimpleNamespace(player=k["player"], fresh=k["fresh"])):
            self.run_main("--loop")
        self.assertEqual([k["oracle"] for k in hooks], [None, None])

    def test_loop_with_laya_parks_checks_for_new_weights_while_waiting_and_resumes(self):
        calls = []

        class SpyReloader:
            def __init__(self, oracle):
                self.oracle = oracle

            def park(self):
                calls.append("park")

            def check(self):
                calls.append("check")

            def resume(self):
                calls.append("resume")

        hooks = []
        polls = []
        real_poll = bot.waiting_poll

        def capture(pad, reloader=None):
            polls.append(real_poll(pad, reloader))
            calls.append("wait")
            return polls[-1]

        with mock.patch.object(bot.laya, "Reloader", SpyReloader), mock.patch.object(bot, "waiting_poll", side_effect=capture), \
                mock.patch.object(bot, "BotHooks", side_effect=lambda *a, **k: hooks.append(k) or SimpleNamespace(player=k["player"], fresh=k["fresh"])):
            code, starts, waits, sessions = self.run_main("--loop", "--laya")
        self.assertEqual((code, waits, len(sessions)), (0, 1, 2))
        self.assertEqual(calls, ["park", "wait", "resume"])
        polls[0]()
        polls[0]()
        self.assertEqual(calls[3:], ["check", "check"])
        self.assertIsInstance(hooks[0]["oracle"], bot.laya.Oracle)
        self.assertIs(hooks[0]["oracle"], hooks[1]["oracle"])
        self.assertEqual(hooks[0]["laya_weight"], 0.3)

    def test_laya_without_loop_has_no_reloader(self):
        with mock.patch.object(bot.laya, "Reloader") as reloader:
            code, starts, waits, sessions = self.run_main("--laya", reasons=(MATCH_OVER,))
        self.assertEqual((code, starts, reloader.call_count), (0, 1, 0))

    def test_background_load_failure_does_not_raise(self):
        logs = []

        def broken(model):
            raise RuntimeError("no gpu")

        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"DATA_DIR": tmp}):
            thread = bot.laya.start_background(log=lambda m, **_: logs.append(m), rounds=1, factory=broken)
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertTrue(thread.daemon)
        self.assertIn("not loaded (no gpu)", logs[-1])


if __name__ == "__main__":
    unittest.main()
