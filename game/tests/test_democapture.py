import random
import unittest

from game.combos import ComboRunner, captured_frames
from game.democapture import build_demo_route, compare, consensus, loops, replay_route, signature, widen
from game.sequencer import Sequencer
from game.tests.test_combocapture import player
from game.tests.test_pad import fake_pad

SUBJECT, TARGET = 0, 1


def demo_frame(f):
    s = {"x": -1000.0}
    if 43 <= f < 63:
        s["dir_held"] = "d"
    if f == 64:
        s.update(buttons_pressed=["1"], buttons_held=["1"])
    if f == 70:
        s.update(buttons_pressed=["2"], buttons_held=["2"])
    if f >= 64:
        s.update(move_id=0x5E1, free_movement=False)
    if f >= 65:
        s.update(move_id=0x696, hit_level="mid")
    if f >= 79:
        s.update(move_id=0x697, hit_level="high")
    if f == 131 or 137 <= f < 152:
        s["dir_held"] = "f"
    if f >= 132:
        s.update(move_id=0x5C1, hit_level="none")
    if f >= 138:
        s["move_id"] = 0x6F6
    if f == 153:
        s.update(dir_held="b", buttons_pressed=["3"], buttons_held=["3"])
    if f >= 154:
        s.update(move_id=0x68E, hit_level="mid")
    health = 190 if f < 77 else 180 if f < 100 else 168 if f < 171 else 158
    t = {"health": health}
    if f >= 77:
        t.update(hit_reaction=12, free_movement=False, move_id=0x773)
    return s, t


def demo_states(loop_count=2, start=0, length=220):
    out = []
    for n in range(loop_count):
        for f in range(start if n == 0 else 0, length):
            s, t = demo_frame(f)
            players = [None, None]
            players[SUBJECT], players[TARGET] = player(**s), player(**t)
            out.append({"frame": f, "players": players, "human_slot": SUBJECT})
    s, t = demo_frame(0)
    out.append({"frame": 0, "players": [player(**s), player(**t)], "human_slot": SUBJECT})
    return out


class DemoCaptureTest(unittest.TestCase):
    def test_loops_split_on_reset_and_skip_partial(self):
        logs = []
        got = list(loops(iter(demo_states(3, start=50)), SUBJECT, logs.append))
        self.assertEqual(len(got), 2)
        self.assertEqual([r["frame"] for r in got[0]][:2], [0, 1])
        self.assertIn("skipped a partial loop", logs[0])

    def test_route_from_demo_loop(self):
        rows = next(loops(iter(demo_states(1)), SUBJECT))
        route = build_demo_route("ws12", rows, SUBJECT, {0x696: "ws1,2"})
        self.assertEqual(route["launcher"], "ws1,2")
        self.assertTrue(route["launcher_inputs_replay"])
        self.assertEqual(route["launcher_inputs"], [[-34, "d", [], 0], [-14, "n", [], 0], [-13, "n", ["1"], 2],
                                                    [-7, "n", ["2"], 2]])
        self.assertEqual(route["hits"], [[0, 10, "0x0696"], [23, 12, "0x0697"], [94, 10, "0x068E"]])
        self.assertEqual(route["inputs"], [[54, "f", [], 0], [55, "n", [], 0], [60, "f", [], 0], [75, "n", [], 0],
                                           [76, "b", ["3"], 2], [77, "n", [], 0]])
        self.assertEqual(route["attacks"], [[2, "0x0697"], [77, "0x068E"]])
        self.assertEqual(route["start_distance"], 1000)
        self.assertEqual(route["damage"], 32)

    def test_identical_loops_match(self):
        a, b = list(loops(iter(demo_states(2)), SUBJECT))
        self.assertEqual(signature(build_demo_route("x", a, SUBJECT)), signature(build_demo_route("x", b, SUBJECT)))

    def test_consensus_recovers_presses_each_loop_missed(self):
        full = list(loops(iter(demo_states(3)), SUBJECT))
        dropped = [[r for r in rows if r["frame"] != skip] for rows, skip in zip(full, (64, 70, 153))]
        self.assertNotEqual(build_demo_route("x", [dict(r) for r in dropped[0]], SUBJECT)["launcher_inputs"],
                            build_demo_route("x", [dict(r) for r in full[0]], SUBJECT)["launcher_inputs"])
        clean = build_demo_route("x", [dict(r) for r in full[0]], SUBJECT)
        voted = build_demo_route("x", consensus(dropped), SUBJECT)
        self.assertEqual(voted["launcher_inputs"], clean["launcher_inputs"])
        self.assertEqual(voted["inputs"], clean["inputs"])
        self.assertEqual(voted["hits"], clean["hits"])

    def test_no_hit_loop_is_skipped(self):
        rows = [{"frame": f, "target_health": 190, "offset": 0} for f in range(10)]
        self.assertIsNone(build_demo_route("x", rows, SUBJECT))

    def test_opener_holds_its_last_direction_until_the_connect(self):
        opener = [[-19, "f", [], 0], [-18, "n", [], 0], [-16, "f", ["2"], 2], [-15, "n", [], 0], [-10, "f", [], 0]]
        frames, start = captured_frames(opener, until=0)
        self.assertEqual(start, -19)
        self.assertEqual(frames[-12:], [("f", ())] * 11 + [("n", ())])
        self.assertEqual(captured_frames(opener)[0][-2:], [("f", ()), ("n", ())])

    def test_widen_keeps_a_release_before_the_same_button(self):
        self.assertEqual(widen([[0, "n", ["1"], 1], [2, "n", ["1"], 1]]), [[0, "n", ["1"], 1], [2, "n", ["1"], 2]])
        self.assertEqual(widen([[0, "n", ["1"], 1], [1, "n", ["2"], 1]]), [[0, "n", ["1"], 2], [1, "n", ["2"], 2]])


LEAD_IN = 14 + 29


def lead_in(runner, seq, start, target, bot, limit=200):
    for f in range(start, start + limit):
        out = runner.on_state({"frame": f, "players": [target, bot]})
        seq.on_frame(f, bot)
        if out is not None:
            return f, out
    return None, None


class DemoReplayTest(unittest.TestCase):
    def test_opener_replays_recorded_inputs(self):
        rows = next(loops(iter(demo_states(1)), SUBJECT))
        route = build_demo_route("ws12", rows, SUBJECT, {0x696: "ws1,2"})
        pad, device = fake_pad()
        seq = Sequencer(pad, 2, rng=random.Random(0))
        runner = ComboRunner(route, seq, 1, name="ws12")
        bot, target = player(side=1), player()
        self.assertEqual(lead_in(runner, seq, 100, target, bot), (100 + LEAD_IN, "ws1,2"))
        self.assertEqual(runner.move.frames, captured_frames(route["launcher_inputs"], until=0)[0])
        self.assertEqual(device.pressed, {"DPAD_DOWN"})

    def test_walks_14_frames_then_stands_30_before_the_opener(self):
        rows = next(loops(iter(demo_states(1)), SUBJECT))
        route = build_demo_route("ws12", rows, SUBJECT, {0x696: "ws1,2"})
        pad, device = fake_pad()
        seq = Sequencer(pad, 2)
        runner = ComboRunner(route, seq, 1, name="ws12")
        bot, target = player(side=0), player(x=500.0)
        pressed = []
        for f in range(100, 100 + LEAD_IN):
            self.assertIsNone(runner.on_state({"frame": f, "players": [target, bot]}))
            seq.on_frame(f, bot)
            pressed.append(set(device.pressed))
        self.assertEqual(pressed[:14], [{"DPAD_RIGHT"}] * 14)
        self.assertEqual(pressed[14:], [set()] * (LEAD_IN - 14))
        self.assertEqual(runner.on_state({"frame": 100 + LEAD_IN, "players": [target, bot]}), "ws1,2")

    def test_counter_hit_route_skips_the_minimum_walk(self):
        rows = next(loops(iter(demo_states(1)), SUBJECT))
        route = replay_route(build_demo_route("ws12", rows, SUBJECT, {0x696: "ws1,2"}), counter_hit=True)
        runner = ComboRunner(route, Sequencer(fake_pad()[0], 2), 1, name="ws12")
        charging = player(buttons_pressed=["1", "2", "3", "4"], buttons_held=["1", "2", "3", "4"])
        self.assertEqual(runner.on_state({"frame": 100, "players": [charging, player(side=1)]}), "ws1,2")

    def test_opener_waits_for_the_demo_start_frame(self):
        rows = next(loops(iter(demo_states(1)), SUBJECT))
        route = build_demo_route("ws12", rows, SUBJECT, {0x696: "ws1,2"})
        self.assertEqual(route["start_round_frame"], 43)
        runner = ComboRunner(route, Sequencer(fake_pad()[0], 2), 1, name="ws12")
        bot, target = player(side=1), player()
        for f in range(30, 43):
            self.assertIsNone(runner.on_state({"frame": f, "players": [target, bot]}))
            self.assertIsNone(runner.approach_start)
        self.assertEqual(lead_in(runner, runner.seq, 43, target, bot), (43 + LEAD_IN, "ws1,2"))

    def test_counter_hit_route_waits_for_ki_charge(self):
        rows = next(loops(iter(demo_states(1)), SUBJECT))
        route = replay_route(build_demo_route("ws12", rows, SUBJECT, {0x696: "ws1,2"}), counter_hit=True)
        runner = ComboRunner(route, Sequencer(fake_pad()[0], 2), 1, name="ws12")
        bot, target = player(side=1), player()
        for f in range(40, 200):
            self.assertIsNone(runner.on_state({"frame": f, "players": [target, bot]}))
        charging = player(buttons_pressed=["1", "2", "3", "4"], buttons_held=["1", "2", "3", "4"])
        self.assertEqual(runner.on_state({"frame": 200, "players": [charging, bot]}), "ws1,2")

    def test_trace_lines_up_replay_and_demo_by_offset(self):
        rows = next(loops(iter(demo_states(1)), SUBJECT))
        route = build_demo_route("ws12", rows, SUBJECT)

        class Run:
            connect_frame = 500
            trace = [{"frame": 500 + k, "pad": ("n", ("1",)) if k == 0 else None, "bot_move": 0x696, "bot_free": False,
                      "target_move": 0x773, "distance": 900, "reaction": 12} for k in range(-5, 3)]

        lines = []
        compare(Run(), route, after=2, log=lambda m, **_: lines.append(m))
        self.assertEqual(len(lines), 9)
        self.assertIn("+0 |    n+1 0x0696", lines[6])
        self.assertTrue(lines[6].endswith("| n 0x0696 0 0x0773  1000 12"), lines[6])
        lines.clear()
        Run.connect_frame = None
        compare(Run(), route, log=lambda m, **_: lines.append(m))
        self.assertEqual(lines, ["  trace: the opener never connected"])

    def test_counter_hit_opener_walks_in_to_the_demo_spacing(self):
        rows = next(loops(iter(demo_states(1)), SUBJECT))
        route = replay_route(build_demo_route("ws12", rows, SUBJECT, {0x696: "ws1,2"}), counter_hit=True)
        route.update(connect_distance=962, opener_reach=590)
        pad, device = fake_pad()
        seq = Sequencer(pad, 2)
        runner = ComboRunner(route, seq, 1, name="ws12")
        bot = player(side=0, x=0.0)
        charging = player(x=1800.0, buttons_pressed=["1", "2", "3", "4"], buttons_held=["1", "2", "3", "4"])
        self.assertIsNone(runner.on_state({"frame": 100, "players": [charging, bot]}))
        seq.on_frame(100, bot)
        self.assertEqual(device.pressed, {"DPAD_RIGHT"})
        self.assertIsNone(runner.on_state({"frame": 101, "players": [player(x=1600.0), bot]}))
        seq.on_frame(101, bot)
        stepping = dict(bot, move_id=0x5C4)
        for f in range(102, 106):
            self.assertIsNone(runner.on_state({"frame": f, "players": [player(x=1550.0), stepping]}))
            seq.on_frame(f, stepping)
            self.assertEqual(device.pressed, set())
        for f in range(106, 135):
            self.assertIsNone(runner.on_state({"frame": f, "players": [player(x=1550.0), bot]}))
            seq.on_frame(f, bot)
        self.assertEqual(runner.on_state({"frame": 135, "players": [player(x=1550.0), bot]}), "ws1,2")
        self.assertEqual(runner.opener_distance, 1550)
        seq.on_frame(135, bot)
        for f in range(136, 150):
            runner.on_state({"frame": f, "players": [player(x=1000.0), dict(bot, free_movement=False)]})
            seq.on_frame(f, bot)
        runner.on_state({"frame": 150, "players": [player(x=800.0, health=180, hit_reaction=10),
                                                   dict(bot, free_movement=False, move_id=0x696)]})
        self.assertEqual(runner.connect_frame, 150)
        self.assertEqual(route["learned_reach"], 750)
        self.assertEqual(runner.fire_distance(), 962 + 750)

    def test_close_enough_connect_keeps_the_reach(self):
        rows = next(loops(iter(demo_states(1)), SUBJECT))
        route = build_demo_route("ws12", rows, SUBJECT, {0x696: "ws1,2"})
        route.update(connect_distance=962, opener_reach=590)
        seq = Sequencer(fake_pad()[0], 2)
        runner = ComboRunner(route, seq, 1, name="ws12")
        bot = player(side=0, x=0.0)
        self.assertEqual(lead_in(runner, seq, 50, player(x=1500.0), bot), (50 + LEAD_IN, "ws1,2"))
        busy = dict(bot, free_movement=False, move_id=0x696)
        runner.on_state({"frame": 100, "players": [player(x=1000.0), busy]})
        seq.on_frame(100, busy)
        runner.on_state({"frame": 101, "players": [player(x=1000.0, health=180, hit_reaction=12), busy]})
        self.assertEqual(runner.reach, 500)
        self.assertNotIn("learned_reach", route)
        self.assertEqual(runner.fire_distance(), 962 + 590)

    def test_whiffed_opener_does_not_teach_reach(self):
        rows = next(loops(iter(demo_states(1)), SUBJECT))
        route = build_demo_route("ws12", rows, SUBJECT, {0x696: "ws1,2"})
        route.update(connect_distance=1285, opener_reach=150)
        seq = Sequencer(fake_pad()[0], 2)
        runner = ComboRunner(route, seq, 1, name="ws12")
        bot = player(side=0, x=0.0)
        self.assertEqual(lead_in(runner, seq, 50, player(x=1400.0), bot), (50 + LEAD_IN, "ws1,2"))
        busy = dict(bot, free_movement=False, move_id=0x697)
        runner.on_state({"frame": 100, "players": [player(x=1100.0), busy]})
        seq.on_frame(100, busy)
        runner.on_state({"frame": 101, "players": [player(x=1100.0, health=178, hit_reaction=12), busy]})
        self.assertEqual(runner.connect_frame, 101)
        self.assertIsNone(runner.reach)
        self.assertNotIn("learned_reach", route)

    def test_unnamed_opener_waits_while_bot_is_busy(self):
        rows = next(loops(iter(demo_states(1)), SUBJECT))
        route = build_demo_route("x", rows, SUBJECT)
        self.assertEqual(route["launcher"], "0x0696")
        seq = Sequencer(fake_pad()[0], 2)
        runner = ComboRunner(route, seq, 1, name="x")
        busy = player(side=1, free_movement=False, frames_until_actionable=10)
        self.assertIsNone(runner.on_state({"frame": 60, "players": [player(), busy]}))
        self.assertIsNone(runner.approach_start)
        self.assertEqual(lead_in(runner, seq, 61, player(), player(side=1)), (61 + LEAD_IN, "0x0696"))

    def test_counter_hit_opener_marks_route(self):
        rows = next(loops(iter(demo_states(1)), SUBJECT))
        for r in rows:
            if r["frame"] >= 77:
                r["target_reaction"] = 10
        route = build_demo_route("ch", rows, SUBJECT)
        self.assertTrue(route["counter_hit"])
        self.assertEqual(route["trigger"], "ki_charge")
        plain = build_demo_route("x", next(loops(iter(demo_states(1)), SUBJECT)), SUBJECT)
        self.assertEqual((plain["counter_hit"], plain["trigger"]), (False, "round_frame"))
        self.assertEqual(replay_route(plain)["trigger"], "round_frame")

    def test_demo_in_heat_marks_route(self):
        states = demo_states(1)
        for gs in states:
            gs["players"][SUBJECT]["heat_active"] = True
        route = build_demo_route("h", next(loops(iter(states), SUBJECT)), SUBJECT)
        self.assertTrue(route["heat"])
        plain = build_demo_route("x", next(loops(iter(demo_states(1)), SUBJECT)), SUBJECT)
        self.assertFalse(plain["heat"])
        self.assertTrue(replay_route(plain, heat=True)["heat"])

    def test_heat_route_bursts_and_waits_out_the_burst_before_walking(self):
        rows = next(loops(iter(demo_states(1)), SUBJECT))
        route = replay_route(build_demo_route("ws12", rows, SUBJECT, {0x696: "ws1,2"}), heat=True)
        pad, device = fake_pad()
        seq = Sequencer(pad, 2)
        runner = ComboRunner(route, seq, 1, name="ws12")
        bot, target = player(side=1), player()
        buttons = {pad.config["buttons"]["2"], pad.config["buttons"]["3"]}
        pressed = []
        for f in range(43, 50):
            self.assertIsNone(runner.on_state({"frame": f, "players": [target, bot]}))
            seq.on_frame(f, bot)
            pressed.append(set(device.pressed))
        self.assertIn(buttons, pressed)
        bursting = dict(bot, heat_active=True, free_movement=False, move_id=0x900)
        for f in range(50, 110):
            self.assertIsNone(runner.on_state({"frame": f, "players": [target, bursting]}))
            seq.on_frame(f, bursting)
        self.assertIsNone(runner.approach_start)
        heated = dict(bot, heat_active=True)
        self.assertEqual(lead_in(runner, seq, 110, target, heated), (110 + LEAD_IN, "ws1,2"))

    def test_heat_followup_runs_right_after_the_burst_then_custom_walk_and_stand(self):
        rows = next(loops(iter(demo_states(1)), SUBJECT))
        route = replay_route(build_demo_route("ws12", rows, SUBJECT, {0x696: "ws1,2"}), heat=True)
        route.update(heat_followup="b,B", heat_followup_hold=10, min_walk_frames=14, idle_frames=20)
        pad, device = fake_pad()
        seq = Sequencer(pad, 2)
        runner = ComboRunner(route, seq, 1, name="ws12")
        bot, target = player(side=0), player(x=500.0)
        buttons = {pad.config["buttons"]["2"], pad.config["buttons"]["3"]}
        pressed = []
        for f in range(43, 60):
            heat = dict(bot, heat_active=f > 44, free_movement=f < 45 or f > 59)
            self.assertIsNone(runner.on_state({"frame": f, "players": [target, heat]}))
            seq.on_frame(f, heat)
            pressed.append(set(device.pressed))
        self.assertEqual(pressed[:2], [buttons, buttons])
        self.assertEqual(pressed[2:4], [{"DPAD_LEFT"}, set()])
        self.assertEqual(pressed[4:14], [{"DPAD_LEFT"}] * 10)
        heated = dict(bot, heat_active=True)
        self.assertEqual(lead_in(runner, seq, 60, target, heated), (60 + 14 + 19, "ws1,2"))

    def test_heat_route_stops_when_heat_never_activates(self):
        rows = next(loops(iter(demo_states(1)), SUBJECT))
        route = replay_route(build_demo_route("ws12", rows, SUBJECT, {0x696: "ws1,2"}), heat=True)
        seq = Sequencer(fake_pad()[0], 2)
        runner = ComboRunner(route, seq, 1, name="ws12")
        bot, target = player(side=1), player()
        for f in range(43, 200):
            runner.on_state({"frame": f, "players": [target, bot]})
            seq.on_frame(f, bot)
        self.assertEqual(runner.status, "aborted")
        self.assertIn("heat burst", runner.reason)


if __name__ == "__main__":
    unittest.main()
