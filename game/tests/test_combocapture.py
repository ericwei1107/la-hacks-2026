import random
import unittest

from game import state as st
from game.combocapture import attack_groups, build_route, derive_events, dump_route, input_events, move_names, record
from game.combos import ComboRunner, captured_frames, captured_links
from game.difficulty import Difficulty
from game.notation import NEUTRAL
from game.sequencer import Sequencer
from game.tests.test_pad import fake_pad

SUBJECT, TARGET = 0, 1


def player(**kw):
    p = {"health": 190, "hit_reaction": 0, "free_movement": True, "frames_until_actionable": 0, "move_id": 0x8001,
         "side": 0, "hit_level": "none", "status": 0, "x": 0.0, "y": 1010.0, "z": 0.0, "basic_state": 3,
         "frame_in_move": 1, "dir_held": "n", "buttons_pressed": [], "buttons_held": []}
    p.update(kw)
    return p


def scripted_take(inputs=True):
    script = {}
    for f in range(100, 140):
        script[f] = ({}, {})
    script[140] = ({"move_id": 0x701, "hit_level": "high", "free_movement": False},
                   {"health": 167, "hit_reaction": 12, "move_id": 0x126, "status": st.JUGGLED_BIT, "free_movement": False})
    for off in range(1, 90):
        s = {"move_id": 0x701, "hit_level": "high", "free_movement": False}
        if off >= 40:
            s = {"move_id": 0x685, "hit_level": "mid", "free_movement": False}
        if off >= 52:
            s = {"move_id": 0x686, "hit_level": "mid", "free_movement": False}
        if inputs:
            if off in (26, 28) or 29 <= off < 38:
                s["dir_held"] = "f"
            if off in (38, 39):
                s["dir_held"] = "b"
                s["buttons_held"] = ["2"]
                if off == 38:
                    s["buttons_pressed"] = ["2"]
            if off in (48, 49):
                s["buttons_held"] = ["2"]
                if off == 48:
                    s["buttons_pressed"] = ["2"]
        t = {"health": 167 if off < 54 else (155 if off < 64 else 141), "hit_reaction": 12, "move_id": 0x126,
             "status": st.JUGGLED_BIT, "free_movement": False}
        if off >= 80:
            t = {"health": 141, "move_id": 0x8006, "status": 0x6084, "free_movement": False}
        script[140 + off] = (s, t)
    states = []
    for f in sorted(script):
        s, t = script[f]
        players = [None, None]
        players[SUBJECT], players[TARGET] = player(**s), player(**t)
        states.append({"frame": f, "players": players, "human_slot": SUBJECT})
    return iter(states)


class CaptureTest(unittest.TestCase):
    def test_record_from_input_fields(self):
        take = record(scripted_take(), SUBJECT)
        self.assertEqual(take["connect_frame"], 140)
        self.assertEqual(take["hits"], [[0, 23, "0x0701"], [54, 12, "0x0686"], [64, 14, "0x0686"]])
        self.assertEqual(take["rows"][-1]["offset"], 80)
        route = build_route("t", take, SUBJECT, "f,n,d,df+2", ["f,n,d,df+2"])
        self.assertEqual(route["source"], "inputs")
        self.assertEqual(route["launcher_move_id"], "0x0701")
        self.assertEqual(route["attacks"], [[40, "0x0685"], [52, "0x0686"]])
        self.assertEqual(route["inputs"], [[26, "f", [], 0], [27, "n", [], 0], [28, "f", [], 0], [38, "b", ["2"], 2],
                                           [40, "n", [], 0], [48, "n", ["2"], 2]])
        self.assertEqual(route["damage"], 49)
        self.assertIn('"inputs": [\n  [26, "f", [], 0],', dump_route(route))

    def test_launcher_from_move_id_and_pre_connect_inputs(self):
        take = record(scripted_take(), SUBJECT)
        route = build_route("t", take, SUBJECT, None, [], {0x701: "f,n,d,df+2", 0x685: "b+2"})
        self.assertEqual(route["launcher"], "f,n,d,df+2")
        self.assertEqual(route["attack_names"], ["b+2", None])
        self.assertEqual(route["launcher_inputs"], [])
        self.assertEqual(build_route("t", take, SUBJECT, None, [], {})["launcher"], "f,n,d,df+2")

    def test_kazuya_move_names(self):
        names = move_names("kazuya")
        self.assertEqual(names[0x701], "f,n,d,df+2")
        self.assertEqual(names[0x6AF], "df+2")

    def test_held_without_pressed_bit_still_counts(self):
        rows = [{"offset": 1, "dir": "n", "pressed": [], "held": ["1"]}, {"offset": 2, "dir": "n", "pressed": [], "held": ["1"]},
                {"offset": 3, "dir": "n", "pressed": [], "held": []}]
        self.assertEqual(input_events(rows), [[1, "n", ["1"], 2]])

    def test_empty_fields_derive_from_move_starts(self):
        take = record(scripted_take(inputs=False), SUBJECT)
        route = build_route("t", take, SUBJECT, "f,n,d,df+2", ["f,n,d,df+2", "f,F,b+2,2", "df+1,df+2"])
        self.assertEqual(route["source"], "moves")
        self.assertEqual(route["notes"], ["2 attack moves after the launcher but 4 inputs in the links; mapped the first 2"])
        self.assertEqual(route["inputs"], [[28, "f", [], 0], [29, "n", [], 0], [30, "f", [], 0], [40, "b", ["2"], 2],
                                           [46, "n", ["2"], 2]])

    def test_attack_groups_mark_string_follow_ups(self):
        self.assertEqual(attack_groups(["f,n,d,df+2", "f,F,b+2,2", "df+1,df+2"]),
                         [("f,n,d,df+2", False), ("f,F,b+2", False), ("2", True), ("df+1", False), ("df+2", True)])
        self.assertEqual(derive_events([[30, "0x6A6"], [44, "0x6AA"]], [("df+1", False), ("df+2", True)]),
                         [[30, "df", ["1"], 2], [37, "df", ["2"], 2]])


class FramesTest(unittest.TestCase):
    def test_events_to_frames(self):
        frames, start = captured_frames([[26, "f", [], 0], [27, "n", [], 0], [28, "f", [], 0], [30, "b", ["2"], 2], [32, "n", [], 0]])
        self.assertEqual(start, 26)
        self.assertEqual(frames, [("f", ()), NEUTRAL, ("f", ()), ("f", ()), ("b", ("2",)), ("b", ("2",)), NEUTRAL, NEUTRAL])

    def test_cut(self):
        frames, start = captured_frames([[5, "n", ["1"], 2], [20, "n", ["2"], 2]], cut=10)
        self.assertEqual((frames, start), ([("n", ("1",)), ("n", ("1",)), NEUTRAL], 5))


ROUTE = {"captured": True, "name": "cap", "launcher": "f,n,d,df+2", "launcher_move_id": "0x0701",
         "inputs": [[26, "f", [], 0], [27, "n", [], 0], [28, "f", [], 0], [38, "b", ["2"], 2], [40, "n", [], 0]],
         "attacks": [[40, "0x0685"]], "hits": [[0, 23, "0x0701"], [54, 12, "0x0685"]], "guide": "cap"}


class Bot:
    def __init__(self, route=ROUTE, difficulty=None, rng=None):
        self.pad, self.device = fake_pad()
        self.seq = Sequencer(self.pad, 2, difficulty=difficulty, rng=rng or random.Random(0))
        self.runner = ComboRunner(route, self.seq, 1, name="cap")
        self.frame = 99
        self.bot = player(side=1)
        self.target = player()

    def step(self, **bot):
        self.frame += 1
        self.bot.update(bot)
        out = self.runner.on_state({"frame": self.frame, "players": [dict(self.target), dict(self.bot)]})
        self.seq.on_frame(self.frame, self.bot)
        return out

    def until(self, frame, **bot):
        while self.frame < frame:
            self.step(**bot)


class CapturedRunnerTest(unittest.TestCase):
    def launch(self, b):
        self.assertEqual(b.step(), "f,n,d,df+2")
        b.until(112, move_id=0x701, hit_level="high", free_movement=False, frames_until_actionable=30)
        b.target["health"] -= 23
        b.target["hit_reaction"] = 12
        b.step()
        self.assertEqual(b.runner.connect_frame, 113)

    def test_links_and_listed(self):
        links = captured_links(ROUTE)
        self.assertEqual([l.notation for l in links], ["f,n,d,df+2", "captured:cap"])
        self.assertEqual(ComboRunner(ROUTE, Sequencer(fake_pad()[0], 2), 1).listed_damage, 35)

    def test_inputs_start_at_connect_plus_offset_minus_latency(self):
        b = Bot()
        self.launch(b)
        self.assertEqual(b.runner.replay.earliest, 113 + 26 - 2)
        b.until(136)
        self.assertIsNone(b.runner.replay.start_frame)
        self.assertEqual(b.device.pressed, set())
        b.step()
        self.assertEqual(b.runner.replay.start_frame, 137)
        self.assertEqual(b.device.pressed, {"DPAD_LEFT"})
        b.until(148)
        b.step()
        self.assertEqual(b.device.pressed, {"DPAD_RIGHT", "Y"})

    def test_done_when_all_hits_land(self):
        b = Bot()
        self.launch(b)
        b.until(152)
        b.step(move_id=0x685, hit_level="mid")
        self.assertEqual(b.runner.status, "running")
        b.until(166)
        b.target["health"] -= 12
        b.step()
        self.assertEqual(b.runner.status, "done")
        self.assertEqual(b.runner.damage, 35)

    def test_diverged_move_aborts(self):
        b = Bot()
        self.launch(b)
        b.until(152)
        b.step(move_id=0x686, hit_level="mid")
        self.assertEqual(b.runner.status, "aborted")
        self.assertIn("diverged: move 0x0686 at +40, expected 0x0685 at +40", b.runner.reason)
        self.assertFalse(b.seq.busy())

    def test_non_attack_moves_are_not_checked(self):
        b = Bot()
        self.launch(b)
        b.step(move_id=0x5C1, hit_level="none")
        b.step(move_id=0x6F6, hit_level="none")
        self.assertEqual(b.runner.status, "running")

    def test_dropped_when_inputs_finish_short(self):
        b = Bot()
        self.launch(b)
        b.until(152)
        b.step(move_id=0x685, hit_level="mid")
        b.until(160)
        self.assertEqual(b.runner.status, "running")
        b.step(free_movement=True, frames_until_actionable=0, move_id=0x8001, hit_level="none")
        self.assertEqual(b.runner.status, "dropped")
        self.assertEqual(b.runner.reason, "inputs finished with 1/2 hits")

    def test_launcher_miss(self):
        b = Bot()
        b.step()
        b.until(130, move_id=0x701, hit_level="high", free_movement=False, frames_until_actionable=5)
        b.step(free_movement=True, move_id=0x8001, hit_level="none")
        self.assertEqual((b.runner.status, b.runner.reason), ("dropped", "launcher missed"))

    def test_short_cut_at_low_levels(self):
        route = dict(ROUTE, hits=[[0, 23, "0x0701"], [39, 12, "0x0685"], [54, 14, "0x0686"]],
                     attacks=[[30, "0x0685"], [45, "0x0686"]],
                     inputs=[[26, "f", [], 0], [28, "b", ["2"], 2], [44, "n", ["2"], 2]])
        runner = ComboRunner(route, Sequencer(fake_pad()[0], 2, difficulty=Difficulty.preset(1)), 1)
        self.assertEqual(runner.planned_hits, 2)
        self.assertEqual(runner.attacks, [[30, "0x0685"]])
        self.assertEqual(runner.cut, 39)
        full = ComboRunner(route, Sequencer(fake_pad()[0], 2, difficulty=Difficulty.preset(4)), 1)
        self.assertEqual(full.planned_hits, 3)

    def test_execution_error_applies_to_replay(self):
        b = Bot(difficulty=Difficulty.preset(3).with_knobs(execution_error=1.0), rng=random.Random(1))
        self.launch(b)
        self.assertIn(1, [link for link, _ in b.runner.errors])
        self.assertNotEqual(b.runner.replay.frames, captured_frames(ROUTE["inputs"])[0])


if __name__ == "__main__":
    unittest.main()
