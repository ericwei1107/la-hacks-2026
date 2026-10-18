import random
import unittest

from game.difficulty import Difficulty
from game.notation import NEUTRAL, compile_notation, runs
from game.sequencer import Sequencer, apply_execution_error
from game.tests.test_pad import fake_pad

EWGF = "f,n,d,df+2"


def bot(free=True, until=0, side=0):
    return {"free_movement": free, "frames_until_actionable": until, "side": side}


def make(latency=2, difficulty=None, rng=None):
    pad, device = fake_pad()
    return Sequencer(pad, latency, difficulty=difficulty, rng=rng), device


def inputs(frames):
    return [mask for mask, _ in runs(frames) if mask != NEUTRAL]


class ScriptedRng:
    def __init__(self, randoms, pick, k=1):
        self.randoms = list(randoms)
        self.pick = pick
        self.k = k

    def random(self):
        return self.randoms.pop(0)

    def choice(self, seq):
        return self.pick if self.pick in seq else seq[0]

    def randint(self, a, b):
        return self.k


class SubmitTest(unittest.TestCase):
    def test_df1_side0(self):
        seq, device = make()
        move = seq.submit("df+1")
        seq.on_frame(100, bot())
        self.assertEqual(move.start_frame, 100)
        self.assertEqual(device.pressed, {"DPAD_DOWN", "DPAD_RIGHT", "X"})
        seq.on_frame(101, bot())
        self.assertEqual(device.pressed, {"DPAD_DOWN", "DPAD_RIGHT", "X"})
        seq.on_frame(102, bot())
        self.assertEqual(device.pressed, set())
        finished = seq.pop_finished()
        self.assertEqual(finished, [move])
        self.assertEqual(move.done_frame, 102)
        self.assertFalse(move.cancelled)
        self.assertEqual(seq.pop_finished(), [])

    def test_df1_side1_mirrors(self):
        seq, device = make()
        seq.submit("df+1")
        seq.on_frame(100, bot(side=1))
        self.assertEqual(device.pressed, {"DPAD_DOWN", "DPAD_LEFT", "X"})

    def test_forward_back_mirror(self):
        for side, f, b in ((0, "DPAD_RIGHT", "DPAD_LEFT"), (1, "DPAD_LEFT", "DPAD_RIGHT")):
            with self.subTest(side=side):
                seq, device = make()
                seq.submit("f")
                seq.on_frame(10, bot(side=side))
                self.assertEqual(device.pressed, {f})
                seq.submit("b")
                seq.on_frame(11, bot(side=side))
                self.assertEqual(device.pressed, {b})

    def test_string_1_1_2(self):
        seq, _ = make()
        seq.submit("1,1,2")
        for frame in range(200, 216):
            seq.on_frame(frame, bot())
        x, y = ("n", ("1",)), ("n", ("2",))
        self.assertEqual(seq.applied, [(200, x), (202, NEUTRAL), (206, x), (208, NEUTRAL), (212, y), (214, NEUTRAL)])
        self.assertEqual([f - 200 for f, m in seq.applied if m == x], [0, 6])
        self.assertEqual([f - 200 for f, m in seq.applied if m == y], [12])


class BufferTest(unittest.TestCase):
    def test_waits_for_free_movement(self):
        seq, device = make()
        move = seq.submit("1")
        for frame, until in zip(range(100, 105), range(5, 0, -1)):
            seq.on_frame(frame, bot(free=False, until=until))
            self.assertIsNone(move.start_frame)
            self.assertEqual(device.pressed, set())
        seq.on_frame(105, bot())
        self.assertEqual(move.start_frame, 105)
        self.assertEqual(device.pressed, {"X"})

    def test_prepress_starts_within_latency(self):
        seq, device = make(latency=2)
        move = seq.submit("1", prepress=True)
        seq.on_frame(100, bot(free=False, until=5))
        seq.on_frame(101, bot(free=False, until=4))
        seq.on_frame(102, bot(free=False, until=3))
        self.assertIsNone(move.start_frame)
        seq.on_frame(103, bot(free=False, until=2))
        self.assertEqual(move.start_frame, 103)
        self.assertEqual(device.pressed, {"X"})

    def test_earliest(self):
        seq, device = make()
        move = seq.submit("1", earliest=110)
        for frame in range(100, 110):
            seq.on_frame(frame, bot())
            self.assertIsNone(move.start_frame)
        self.assertEqual(device.pressed, set())
        seq.on_frame(110, bot())
        self.assertEqual(move.start_frame, 110)


class FrameIndexTest(unittest.TestCase):
    def test_skipped_frames_use_round_frame_index(self):
        seq, device = make()
        seq.submit(EWGF)
        seq.on_frame(100, bot())
        self.assertEqual(device.pressed, {"DPAD_RIGHT"})
        mask = seq.on_frame(103, bot())
        self.assertEqual(mask, ("df", ("2",)))
        self.assertEqual(device.pressed, {"DPAD_DOWN", "DPAD_RIGHT", "Y"})

    def test_counter_backward_cancels(self):
        seq, device = make()
        move = seq.submit("F")
        seq.on_frame(100, bot())
        seq.on_frame(101, bot())
        self.assertEqual(device.pressed, {"DPAD_RIGHT"})
        seq.on_frame(5, bot())
        self.assertTrue(move.cancelled)
        self.assertEqual(move.done_frame, 5)
        self.assertIsNone(seq.active)
        self.assertEqual(device.pressed, set())
        self.assertEqual(seq.pop_finished(), [move])

    def test_not_live_cancels_and_applies_nothing(self):
        seq, device = make()
        first = seq.submit("F")
        second = seq.submit("1")
        seq.hold("db")
        seq.on_frame(100, bot())
        self.assertEqual(device.pressed, {"DPAD_RIGHT"})
        applied = len(seq.applied)
        seq.on_frame(101, bot(), live=False)
        self.assertTrue(first.cancelled)
        self.assertTrue(second.cancelled)
        self.assertEqual(device.pressed, set())
        self.assertFalse(seq.busy())
        for frame in range(102, 110):
            self.assertIsNone(seq.on_frame(frame, bot(), live=False))
        self.assertEqual(len(seq.applied), applied)
        self.assertEqual(device.pressed, set())
        third = seq.submit("2")
        seq.on_frame(110, bot())
        self.assertEqual(third.start_frame, 110)
        self.assertEqual(device.pressed, {"Y"})


class HoldTest(unittest.TestCase):
    def test_hold_and_override(self):
        seq, device = make()
        seq.hold("db")
        seq.on_frame(100, bot())
        self.assertEqual(device.pressed, {"DPAD_DOWN", "DPAD_LEFT"})
        move = seq.submit("1")
        seq.on_frame(101, bot())
        self.assertEqual(move.start_frame, 101)
        self.assertEqual(device.pressed, {"X"})
        seq.on_frame(102, bot())
        self.assertEqual(device.pressed, {"X"})
        seq.on_frame(103, bot())
        self.assertEqual(move.done_frame, 103)
        self.assertEqual(device.pressed, {"DPAD_DOWN", "DPAD_LEFT"})

    def test_hold_side1(self):
        seq, device = make()
        seq.hold("db")
        seq.on_frame(100, bot(side=1))
        self.assertEqual(device.pressed, {"DPAD_DOWN", "DPAD_RIGHT"})


class ExecutionErrorTest(unittest.TestCase):
    def test_rate_at_level_1(self):
        seq, _ = make(difficulty=Difficulty.preset(1), rng=random.Random(7))
        moves = [seq.submit(EWGF) for _ in range(2000)]
        errors = [m.error for m in moves if m.error]
        self.assertTrue(0.11 <= len(errors) / 2000 <= 0.19, len(errors))
        delays = [e for e in errors if e.startswith("delayed")]
        self.assertTrue(0.55 <= len(delays) / len(errors) <= 0.78, (len(delays), len(errors)))
        clean = compile_notation(EWGF)
        self.assertTrue(all(m.frames == clean for m in moves if not m.error))

    def test_no_errors_at_level_5(self):
        seq, _ = make(difficulty=Difficulty.preset(5), rng=random.Random(7))
        moves = [seq.submit(EWGF) for _ in range(2000)]
        self.assertEqual([m for m in moves if m.error], [])

    def test_no_errors_without_difficulty_or_when_disabled(self):
        seq, _ = make()
        self.assertIsNone(seq.submit(EWGF).error)
        seq, _ = make(difficulty=Difficulty.preset(1).with_knobs(execution_error=1.0))
        self.assertIsNone(seq.submit(EWGF, error=False).error)
        self.assertIsNotNone(seq.submit(EWGF).error)

    def test_delay_keeps_order(self):
        clean = compile_notation(EWGF)
        for pick in (0, 2, 3):
            for k in (1, 2):
                with self.subTest(pick=pick, k=k):
                    frames, why = apply_execution_error(clean, 1.0, ScriptedRng([0.0, 0.0], pick, k))
                    self.assertEqual(why, f"delayed input {pick} by {k}")
                    self.assertEqual(len(frames), len(clean) + k)
                    self.assertEqual(inputs(frames), inputs(clean))
                    self.assertEqual(frames[:pick], clean[:pick])
                    self.assertEqual(frames[pick + k:], clean[pick:])

    def test_delay_of_final_input_still_presses_df2_together(self):
        clean = compile_notation(EWGF)
        frames, _ = apply_execution_error(clean, 1.0, ScriptedRng([0.0, 0.0], 3, 2))
        self.assertEqual(frames, [("f", ()), NEUTRAL, ("d", ()), ("d", ()), ("d", ()), ("df", ("2",)), ("df", ("2",))])

    def test_drop_removes_one_run(self):
        clean = compile_notation(EWGF)
        expected = {0: [("d", ()), ("df", ("2",))], 2: [("f", ()), ("df", ("2",))], 3: [("f", ()), ("d", ())]}
        for pick, kept in expected.items():
            with self.subTest(pick=pick):
                frames, why = apply_execution_error(clean, 1.0, ScriptedRng([0.0, 0.9], pick))
                self.assertEqual(why, f"dropped input {pick}")
                self.assertEqual(len(frames), len(clean))
                self.assertEqual(inputs(frames), kept)

    def test_drop_of_two_frame_press(self):
        clean = compile_notation("1,1,2")
        frames, why = apply_execution_error(clean, 1.0, ScriptedRng([0.0, 0.9], 6))
        self.assertEqual(why, "dropped input 6")
        self.assertEqual(frames, compile_notation("1,1,2")[:6] + [NEUTRAL] * 6 + [("n", ("2",))] * 2)

    def test_no_error_when_roll_misses(self):
        clean = compile_notation(EWGF)
        frames, why = apply_execution_error(clean, 0.15, ScriptedRng([0.5], 0))
        self.assertIs(frames, clean)
        self.assertIsNone(why)
        self.assertEqual(apply_execution_error(clean, 0.0, random.Random(1)), (clean, None))


if __name__ == "__main__":
    unittest.main()
