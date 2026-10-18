import unittest

from game.notation import NEUTRAL, NotationError, Timing, compile_notation, describe, parse

ROUND_TRIPS = ("df+1", "1,1,2", "f,n,d,df+2", "f,n,d,df+4", "ws+2", "2+3", "db+1+2")


def n(count):
    return [NEUTRAL] * count


def press(direction, *buttons):
    return [(direction, tuple(buttons))] * 2


class RoundTripTest(unittest.TestCase):
    def test_text_round_trip(self):
        for text in ROUND_TRIPS:
            with self.subTest(text=text):
                self.assertEqual(describe(compile_notation(text)), text)

    def test_frame_round_trip(self):
        for text in ROUND_TRIPS:
            with self.subTest(text=text):
                frames = compile_notation(text)
                self.assertEqual(compile_notation(describe(frames)), frames)

    def test_hcf_frame_round_trip(self):
        frames = compile_notation("f,hcf+1")
        self.assertEqual(compile_notation(describe(frames)), frames)
        self.assertEqual(describe(frames), "f,b,db,d,df,f+1")
        self.assertEqual(frames, [("f", ()), ("b", ()), ("db", ()), ("d", ()), ("df", ())] + press("f", "1"))


class FrameListTest(unittest.TestCase):
    def test_df1(self):
        self.assertEqual(compile_notation("df+1"), [("df", ("1",)), ("df", ("1",))])

    def test_string_1_1_2(self):
        frames = compile_notation("1,1,2")
        self.assertEqual(len(frames), 14)
        self.assertEqual(frames, press("n", "1") + n(4) + press("n", "1") + n(4) + press("n", "2"))
        self.assertEqual([i for i, m in enumerate(frames) if m != NEUTRAL], [0, 1, 6, 7, 12, 13])

    def test_ewgf(self):
        frames = compile_notation("f,n,d,df+2")
        self.assertEqual(frames, [("f", ()), ("n", ()), ("d", ()), ("df", ("2",)), ("df", ("2",))])
        self.assertEqual(frames[3], ("df", ("2",)))
        self.assertEqual(frames[2], ("d", ()))
        self.assertNotIn("2", frames[2][1])

    def test_f_n_d_df4(self):
        self.assertEqual(compile_notation("f,n,d,df+4"),
                         [("f", ()), ("n", ()), ("d", ()), ("df", ("4",)), ("df", ("4",))])

    def test_ws2(self):
        self.assertEqual(compile_notation("ws+2"), [("d", ())] * 6 + [("n", ())] + [("n", ("2",))] * 2)

    def test_two_plus_three(self):
        self.assertEqual(compile_notation("2+3"), [("n", ("2", "3"))] * 2)

    def test_db12(self):
        self.assertEqual(compile_notation("db+1+2"), [("db", ("1", "2"))] * 2)


class RuleTest(unittest.TestCase):
    def test_slash_diagonal(self):
        self.assertEqual(compile_notation("d/f+1"), compile_notation("df+1"))

    def test_button_order(self):
        self.assertEqual(compile_notation("1+2"), compile_notation("2+1"))
        self.assertEqual(parse("2+1")[0].buttons, ("1", "2"))

    def test_repeat_direction_gets_neutral(self):
        self.assertEqual(compile_notation("f,f"), [("f", ()), NEUTRAL, ("f", ())])

    def test_colon_is_next_frame(self):
        frames = compile_notation("1:2")
        self.assertEqual(frames[0], ("n", ("1",)))
        self.assertEqual(frames[1], ("n", ("2",)))

    def test_hold(self):
        self.assertEqual(compile_notation("F"), [("f", ())] * 10)

    def test_custom_string_gap(self):
        frames = compile_notation("1,1", Timing(string_gap=8))
        self.assertEqual(frames, press("n", "1") + n(6) + press("n", "1"))
        self.assertEqual(frames[8], ("n", ("1",)))

    def test_errors(self):
        for text in ("", "x", "ws", "df+5", "fd+1", "ws+f"):
            with self.subTest(text=text):
                with self.assertRaises(NotationError):
                    compile_notation(text)


if __name__ == "__main__":
    unittest.main()
