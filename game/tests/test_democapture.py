import random
import unittest

from game.combos import ComboRunner, captured_frames
from game.democapture import build_demo_route, consensus, loops, signature, widen
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

    def test_widen_keeps_a_release_before_the_same_button(self):
        self.assertEqual(widen([[0, "n", ["1"], 1], [2, "n", ["1"], 1]]), [[0, "n", ["1"], 1], [2, "n", ["1"], 2]])
        self.assertEqual(widen([[0, "n", ["1"], 1], [1, "n", ["2"], 1]]), [[0, "n", ["1"], 2], [1, "n", ["2"], 2]])


class DemoReplayTest(unittest.TestCase):
    def test_opener_replays_recorded_inputs(self):
        rows = next(loops(iter(demo_states(1)), SUBJECT))
        route = build_demo_route("ws12", rows, SUBJECT, {0x696: "ws1,2"})
        pad, device = fake_pad()
        seq = Sequencer(pad, 2, rng=random.Random(0))
        runner = ComboRunner(route, seq, 1, name="ws12")
        bot, target = player(side=1), player()
        self.assertEqual(runner.on_state({"frame": 100, "players": [target, bot]}), "ws1,2")
        self.assertEqual(runner.move.frames, captured_frames(route["launcher_inputs"])[0])
        seq.on_frame(100, bot)
        self.assertEqual(device.pressed, {"DPAD_DOWN"})


if __name__ == "__main__":
    unittest.main()
