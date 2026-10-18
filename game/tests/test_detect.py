import unittest
from collections import Counter
from pathlib import Path

from game.detect import Detector
from game.options import load_fallback, normalize_table
from game.replay_learn import run_detector
from game.state import Tracker, build_state
from game.summarize import load_jsonl
from game.tests.test_state import EVENT_V, SID, exchange, idle

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"
TABLE = normalize_table(load_fallback()["kazuya"])
LOW = 0x20000112
SPECIAL_LOW = 0x60000402
MID = 0x8000020A
HIGH = 0xA000050F
THROW_LEVEL = 0x60000A1D
PRESS_2 = 0xE000001F
DIR = {"n": 32, "b": 16, "d": 4, "db": 2, "df": 8, "u": 256, "f": 64}
BUTTON_2 = 0x2
D4, DF1, JAB, THROW_ATTEMPT = 0x6DB, 0x6A6, 0x643, 0x70E


def run(frames, subject=0, table=TABLE, human_slot=0):
    tracker = Tracker(SID)
    det = Detector(subject, table)
    events, decisions = [], []
    for f, pair in frames:
        state = build_state(pair, human_slot, f, SID)
        evs = tracker.step(state)
        decisions += det.step(state, evs)
        events += evs
    return events, decisions, det


def low_exchange(reaction, level_code=LOW, level="low", damage=6):
    def_move = 0x728 if reaction == 2 else 0x600
    return exchange(attacker=1, move=D4, total=46, connect_at=12, level_code=level_code, level=level, reaction=reaction,
                    def_move=def_move, def_total=20, damage=damage, tail=10)


def blocked_df1(def_total=19, tail=45):
    return exchange(attacker=1, move=DF1, total=41, connect_at=15, level_code=MID, level="mid", reaction=1, def_move=0x720,
                    def_total=def_total, tail=tail)


def respond(seq, free_frame, patch):
    for f, pair in seq:
        if f >= free_frame:
            patch(f, pair[0])
    return seq


def bot_attack(start=100, length=41, first=15, last=16, level_code=MID, level="mid", move=DF1, lead=3, tail=8, human=None):
    frames = []
    for f in range(start - lead, start + length + tail):
        pair = [idle(0, f), idle(1, f)]
        if start <= f < start + length:
            pair[1].update(move_id=move, frame_in_move=f - start + 1, move_total=length, free_movement=0, hit_level=level_code,
                           hit_level_name=level, first_active=first, last_active=last)
        if human:
            human(f, pair[0])
        frames.append((f, pair))
    return frames


def throw_frames(start=100, connect=105, end=160, press_at=None, damage_at=None):
    frames = []
    for f in range(start, end):
        a, d = idle(1, f), idle(0, f)
        if f > start:
            a.update(move_id=0x7DF, frame_in_move=f - start, move_total=60, free_movement=0, hit_level=THROW_LEVEL, hit_level_name="throw")
        if f >= connect:
            d.update(move_id=0x7E0, frame_in_move=f - connect + 1, move_total=60, free_movement=0, being_thrown=PRESS_2)
        if press_at is not None and f == press_at:
            d.update(game_buttons=0x03FC0000 | BUTTON_2)
        if press_at is not None and f > press_at:
            d.update(throw_escape_flags=0x800)
        if damage_at is not None and f >= damage_at:
            d.update(health=150)
        frames.append((f, [d, a]))
    return frames


def only(test, decisions, situation, action, correct):
    decisions = [d for d in decisions if d["situation"] == situation]
    test.assertEqual(len(decisions), 1, decisions)
    ev = decisions[0]
    test.assertEqual((ev["situation"], ev["action"], ev["detail"]["correct"]), (situation, action, correct))
    test.assertEqual((ev["t"], ev["kind"], ev["actor"], ev["target"], ev["round"]), ("event", "decision_point", 0, 1, 1))
    test.assertEqual([e.message for e in EVENT_V.iter_errors(ev)], [])
    test.assertTrue(ev["detail"]["state_text"].endswith("The stage is open."))
    return ev


class LowDefenseTest(unittest.TestCase):
    def test_hit_standing(self):
        seq, c, _ = low_exchange(reaction=12)
        _, decisions, _ = run(seq)
        ev = only(self, decisions, "low_defense", "hit", False)
        self.assertEqual(ev["move_id"], D4)
        self.assertEqual(ev["detail"]["start_frame"], c)
        self.assertEqual(ev["detail"]["damage"], 6)
        self.assertGreaterEqual(ev["frame"], c)

    def test_blocked_crouching(self):
        seq, c, _ = low_exchange(reaction=2, damage=0)
        _, decisions, _ = run(seq)
        only(self, decisions, "low_defense", "blocked", True)

    def test_special_low_ignored(self):
        seq, c, _ = low_exchange(reaction=12, level_code=SPECIAL_LOW, level="special_low")
        _, decisions, _ = run(seq)
        self.assertEqual([d for d in decisions if d["situation"] == "low_defense"], [])

    def test_jumped(self):
        def airborne(f, human):
            if 105 <= f <= 125:
                human.update(basic_state=25)

        frames = bot_attack(length=46, first=12, last=12, level_code=LOW, level="low", move=D4, human=airborne)
        events, decisions, _ = run(frames)
        self.assertTrue(any(e["kind"] == "whiff" and e["actor"] == 1 for e in events))
        only(self, decisions, "low_defense", "jumped", False)

    def test_whiff_out_of_range_not_counted(self):
        frames = bot_attack(length=46, first=12, last=12, level_code=LOW, level="low", move=D4)
        _, decisions, _ = run(frames)
        self.assertEqual([d for d in decisions if d["situation"] == "low_defense"], [])


class AfterBlockTest(unittest.TestCase):
    def setup(self, def_total=19):
        seq, c, _ = blocked_df1(def_total)
        return seq, c, c + def_total + 1

    def test_block_high(self):
        seq, c, free = self.setup()
        respond(seq, free, lambda f, h: h.update(dir_held=DIR["b"]))
        _, decisions, _ = run(seq)
        ev = only(self, decisions, "after_block:df1", "block_high", True)
        self.assertEqual(ev["move_id"], DF1)
        self.assertEqual(ev["detail"]["start_frame"], c)
        self.assertEqual(ev["detail"]["adv"], 7)
        self.assertEqual(ev["frame"], free + 20)

    def test_block_low_and_duck(self):
        seq, c, free = self.setup()
        respond(seq, free, lambda f, h: h.update(dir_held=DIR["db"]))
        only(self, run(seq)[1], "after_block:df1", "block_low", False)
        seq, c, free = self.setup()
        respond(seq, free, lambda f, h: h.update(dir_held=DIR["d"]))
        only(self, run(seq)[1], "after_block:df1", "duck", False)

    def test_none(self):
        seq, c, free = self.setup()
        only(self, run(seq)[1], "after_block:df1", "none", False)

    def test_press_small_disadvantage_is_wrong(self):
        seq, c, free = self.setup()

        def press(f, h):
            if f >= free + 2:
                h.update(move_id=JAB, frame_in_move=f - free - 1, move_total=27, free_movement=0, hit_level=HIGH, hit_level_name="high")

        respond(seq, free, press)
        ev = only(self, run(seq)[1], "after_block:df1", "press", False)
        self.assertEqual(ev["detail"]["response_move_id"], JAB)
        self.assertEqual(ev["frame"], free + 2 + 12)

    def test_press_at_big_advantage_is_right(self):
        seq, c, free = self.setup(def_total=5)

        def press(f, h):
            if f >= free + 1:
                h.update(move_id=JAB, frame_in_move=f - free, move_total=27, free_movement=0, hit_level=HIGH, hit_level_name="high")

        respond(seq, free, press)
        ev = only(self, run(seq)[1], "after_block:df1", "press", True)
        self.assertGreaterEqual(ev["detail"]["adv"], 10)
        seq, c, free = self.setup(def_total=5)
        respond(seq, free, lambda f, h: h.update(dir_held=DIR["b"]))
        only(self, run(seq)[1], "after_block:df1", "block_high", False)

    def test_sidestep_tap(self):
        seq, c, free = self.setup()
        respond(seq, free, lambda f, h: h.update(dir_held=DIR["u"]) if f in (free + 2, free + 3) else None)
        ev = only(self, run(seq)[1], "after_block:df1", "ss_left", True)
        self.assertEqual(ev["detail"]["evidence"], "input")
        seq, c, free = self.setup()
        respond(seq, free, lambda f, h: h.update(dir_held=DIR["d"]) if f in (free + 2, free + 3) else None)
        only(self, run(seq)[1], "after_block:df1", "ss_right", True)

    def test_sidestep_by_displacement(self):
        seq, c, free = self.setup()
        respond(seq, free, lambda f, h: h.update(position=(-6000.0 + 20.0 * (f - free), 1040.0, -1000.0)))
        ev = only(self, run(seq)[1], "after_block:df1", "ss_left", True)
        self.assertEqual(ev["detail"]["evidence"], "displacement")
        seq, c, free = self.setup()
        respond(seq, free, lambda f, h: h.update(position=(-6000.0 - 20.0 * (f - free), 1040.0, -1000.0)))
        only(self, run(seq)[1], "after_block:df1", "ss_right", True)

    def test_input_and_displacement_agree(self):
        seq, c, free = self.setup()
        respond(seq, free, lambda f, h: h.update(dir_held=DIR["u"]) if f in (free + 2, free + 3) else None)
        by_input = only(self, run(seq)[1], "after_block:df1", "ss_left", True)
        seq, c, free = self.setup()
        respond(seq, free, lambda f, h: h.update(position=(-6000.0 + 20.0 * (f - free), 1040.0, -1000.0)))
        by_move = only(self, run(seq)[1], "after_block:df1", "ss_left", True)
        self.assertEqual(by_input["action"], by_move["action"])

    def test_crouch_dash_is_not_a_sidestep(self):
        seq, c, free = self.setup()
        pattern = {free + 2: DIR["d"], free + 3: DIR["df"], free + 4: DIR["df"], free + 5: DIR["df"]}
        respond(seq, free, lambda f, h: h.update(dir_held=pattern.get(f, DIR["n"])))
        decisions = [d for d in run(seq)[1] if d["situation"] == "after_block:df1"]
        self.assertEqual(len(decisions), 1)
        self.assertNotIn(decisions[0]["action"], ("ss_left", "ss_right"))
        seq, c, free = self.setup()
        pattern = {free + 2: DIR["d"], free + 3: DIR["db"]}
        respond(seq, free, lambda f, h: h.update(dir_held=pattern.get(f, DIR["n"])))
        decisions = [d for d in run(seq)[1] if d["situation"] == "after_block:df1"]
        self.assertNotIn(decisions[0]["action"], ("ss_left", "ss_right"))

    def test_knockback_is_not_movement(self):
        seq, c, free = self.setup()

        def knocked(f, h):
            if f >= free + 3:
                h.update(position=(-6000.0 + 60.0 * (f - free - 2), 1040.0, -1000.0 - 40.0 * (f - free - 2)), hit_reaction=3,
                         move_id=0x600, frame_in_move=f - free - 2, move_total=25, free_movement=0)

        respond(seq, free, knocked)
        decisions = [d for d in run(seq)[1] if d["situation"] == "after_block:df1"]
        self.assertEqual(len(decisions), 1)
        self.assertNotIn(decisions[0]["action"], ("ss_left", "ss_right", "backdash"))

    def test_buffered_punish_counts_as_press(self):
        seq, c, free = self.setup(def_total=5)

        def buffered(f, h):
            if f >= free:
                h.update(move_id=JAB, frame_in_move=f - free + 1, move_total=27, free_movement=0, hit_level=HIGH, hit_level_name="high")

        respond(seq, free, buffered)
        ev = only(self, run(seq)[1], "after_block:df1", "press", True)
        self.assertTrue(ev["detail"]["buffered"])
        self.assertEqual(ev["detail"]["response_move_id"], JAB)
        self.assertEqual(ev["frame"], free + 12)

    def test_string_opens_one_window_and_a_hit_cancels(self):
        first, c1, end1 = blocked_df1(def_total=19, tail=0)
        second, c2, end2 = exchange(attacker=1, move=0x6A7, total=41, connect_at=15, level_code=MID, level="mid", reaction=1,
                                    def_move=0x720, def_total=19, tail=45, start=end1 + 1)
        seq = first + second
        decisions = [d for d in run(seq)[1] if d["situation"].startswith("after_block")]
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["situation"], "after_block:0x6a7")
        first, c1, end1 = blocked_df1(def_total=19, tail=0)
        hit_after, c2, end2 = exchange(attacker=1, move=0x6A7, total=41, connect_at=15, level_code=MID, level="mid", reaction=3,
                                       def_move=0x600, def_total=25, damage=12, tail=45, start=end1 + 1)
        seq = first + hit_after
        decisions = [d for d in run(seq)[1] if d["situation"].startswith("after_block")]
        self.assertEqual(decisions, [])

    def test_backdash_taps(self):
        seq, c, free = self.setup()
        pattern = {free + 2: DIR["b"], free + 3: DIR["n"], free + 4: DIR["b"]}
        respond(seq, free, lambda f, h: h.update(dir_held=pattern.get(f, DIR["n"])))
        ev = only(self, run(seq)[1], "after_block:df1", "backdash", True)
        self.assertEqual(ev["detail"]["evidence"], "input")

    def test_backdash_by_displacement(self):
        seq, c, free = self.setup()
        respond(seq, free, lambda f, h: h.update(position=(-6000.0, 1040.0, -1000.0 - 30.0 * (f - free))))
        ev = only(self, run(seq)[1], "after_block:df1", "backdash", True)
        self.assertEqual(ev["detail"]["evidence"], "displacement")

    def test_throw_attempt(self):
        seq, c, free = self.setup()

        def throw(f, pair):
            if f >= free + 2:
                pair[0].update(move_id=THROW_ATTEMPT, frame_in_move=f - free - 1, move_total=45, free_movement=0, hit_level=HIGH,
                               hit_level_name="high")
            if f >= free + 8:
                pair[1].update(being_thrown=PRESS_2, move_id=0x7E0, frame_in_move=f - free - 7, move_total=60, free_movement=0)

        for f, pair in seq:
            throw(f, pair)
        only(self, run(seq)[1], "after_block:df1", "throw", False)

    def test_unknown_move_uses_hex_key(self):
        seq, c, free = blocked_df1()[0], None, None
        for f, pair in seq:
            if pair[1]["move_id"] == DF1:
                pair[1]["move_id"] = 0x6B8
        decisions = [d for d in run(seq)[1] if d["situation"].startswith("after_block")]
        self.assertEqual(decisions[0]["situation"], "after_block:0x6b8")


class ThrowBreakTest(unittest.TestCase):
    def test_break_with_2(self):
        events, decisions, _ = run(throw_frames(press_at=108))
        self.assertTrue(any(e["kind"] == "throw_break" and e["actor"] == 0 for e in events))
        ev = only(self, decisions, "throw_break", "break_2", True)
        self.assertEqual(ev["detail"]["code"], "press_2")
        self.assertEqual(ev["detail"]["start_frame"], 105)

    def test_no_break(self):
        _, decisions, _ = run(throw_frames(damage_at=125))
        ev = only(self, decisions, "throw_break", "none", False)
        self.assertEqual(ev["frame"], 125)


class SidestepDirTest(unittest.TestCase):
    def test_step_left(self):
        frames = bot_attack(human=lambda f, h: h.update(dir_held=DIR["u"]) if f in (102, 103) else None)
        ev = only(self, run(frames)[1], "sidestep_dir", "left", True)
        self.assertEqual(ev["move_id"], DF1)
        self.assertEqual(ev["detail"]["start_frame"], 100)

    def test_no_step(self):
        ev = only(self, run(bot_attack())[1], "sidestep_dir", "none", False)
        self.assertEqual(ev["frame"], 115)

    def test_not_opened_when_subject_busy(self):
        frames = bot_attack(human=lambda f, h: h.update(free_movement=0, move_id=0x604, frame_in_move=3, move_total=30))
        self.assertEqual([d for d in run(frames)[1] if d["situation"] == "sidestep_dir"], [])


class ResetTest(unittest.TestCase):
    def test_round_reset_drops_pending(self):
        seq, c, _ = blocked_df1(tail=2)
        _, decisions, det = run(seq)
        self.assertEqual([d for d in decisions if d["situation"].startswith("after_block")], [])
        self.assertEqual([o["kind"] for o in det.pending], ["after_block"])
        tracker = Tracker(SID)
        for f in range(0, 5):
            state = build_state([idle(0, f), idle(1, f)], 0, f, SID)
            det.step(state, tracker.step(state))
        self.assertEqual(det.pending, [])


class SampleTest(unittest.TestCase):
    def counts(self, decisions):
        return Counter(d["situation"] for d in decisions)

    def test_versus_sample_human(self):
        states = [r for r in load_jsonl(SAMPLES / "versus_djin_vs_kaz_l3.zip") if r.get("t") == "state"]
        _, decisions, det = run_detector(states, "human", "versus")
        self.assertEqual(det.subject, 0)
        self.assertEqual(Counter((d["situation"], d["action"]) for d in decisions), {("low_defense", "hit"): 1})
        again = run_detector(states, "human", "versus")[1]
        self.assertEqual(decisions, again)

    def test_versus_sample_mirror(self):
        states = [r for r in load_jsonl(SAMPLES / "versus_djin_vs_kaz_l3.zip") if r.get("t") == "state"]
        _, decisions, det = run_detector(states, "bot", "versus")
        self.assertEqual(det.subject, 1)
        counts = self.counts(decisions)
        self.assertGreaterEqual(sum(n for s, n in counts.items() if s.startswith("after_block:")), 5)
        self.assertGreaterEqual(counts["low_defense"], 20)
        self.assertEqual(counts["throw_break"], 4)
        self.assertGreaterEqual(counts["sidestep_dir"], 50)
        for ev in decisions:
            self.assertEqual([e.message for e in EVENT_V.iter_errors(ev)], [], ev)
            self.assertTrue(ev["detail"]["state_text"])
            self.assertEqual(ev["actor"], 1)
        breaks = [d for d in decisions if d["situation"] == "throw_break"]
        self.assertTrue(all(d["action"] == "break_2" and d["detail"]["correct"] for d in breaks))


if __name__ == "__main__":
    unittest.main()
