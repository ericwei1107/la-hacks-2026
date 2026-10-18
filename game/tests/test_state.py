import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from game.reader import decode_health, rotl64
from game.recorder import Recorder, result_text, session_meta
from game.state import Tracker, advantage, build_player, build_state, derive, lying, session_id

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
SID = "2026-10-17T13-05-00_sahil_djin_vs_kaz"
NONE_CODE = 0xC000001D
JAB = 0x643
DF1 = 0x69B
HIGH = 0xA000050F
MID = 0xA0000510
THROW_LEVEL = 0xA0000520


def load_schema(name):
    return json.loads((CONTRACTS / f"{name}.schema.json").read_text())


STATE_V = Draft202012Validator(load_schema("gamestate"), format_checker=FormatChecker())
EVENT_V = Draft202012Validator(load_schema("event"), format_checker=FormatChecker())
SESSION_V = Draft202012Validator(load_schema("session"), format_checker=FormatChecker())

BASE = {
    0: {"slot": 0, "character_id": 12, "character": "devil_jin", "position": (-6000.0, 1040.0, -1000.0), "side": 0},
    1: {"slot": 1, "character_id": 8, "character": "kazuya", "position": (-6000.0, 1040.0, 1000.0), "side": 1},
}


def idle(slot, frame=0, **overrides):
    raw = {
        "health": 190,
        "recoverable_limit": 190,
        "max_health": 190,
        "facing": 0,
        "move_id": 0x8001,
        "frame_in_move": frame % 100 + 1,
        "move_total": 100,
        "free_movement": 1,
        "hit_level": NONE_CODE,
        "hit_level_name": "none",
        "hit_reaction": 0,
        "status": 0x1942,
        "basic_state": 3,
        "being_thrown": NONE_CODE,
        "throw_escape_flags": 0,
        "heat_gauge": NONE_CODE,
        "heat_active": 0,
        "heat_used": 0,
        "rage_active": 0,
        "power_crush": 0,
        "first_active": 0,
        "last_active": 0,
        "first_airborne": 0,
        "last_airborne": 0,
        "dir_held": 32,
        "game_buttons": 0x03FC0000,
        "round_frame": frame,
        "move_record": 0,
    }
    raw.update(BASE[slot])
    raw.update(overrides)
    return raw


def idle_frames(frames):
    return [(f, [idle(0, f), idle(1, f)]) for f in frames]


def exchange(attacker=0, move=JAB, total=27, connect_at=10, level_code=HIGH, level="high", reaction=1,
             def_move=0x604, def_total=18, damage=0, start=100, lead=3, tail=4):
    d = 1 - attacker
    c = start + connect_at - 1
    att_end = start + total
    def_end = c + def_total + 1
    seq = []
    for f in range(start - lead, max(att_end, def_end) + tail):
        a = idle(attacker, f)
        o = idle(d, f)
        if start <= f < att_end:
            a.update(move_id=move, frame_in_move=f - start + 1, move_total=total, free_movement=0,
                     hit_level=level_code, hit_level_name=level)
        if f == c:
            o.update(move_id=0x5C6, frame_in_move=1, move_total=def_total, free_movement=0, hit_reaction=reaction)
        elif c < f < def_end:
            o.update(move_id=def_move, frame_in_move=f - c, move_total=def_total, free_movement=0, hit_reaction=reaction)
        if f >= c:
            o["health"] = 190 - damage
        pair = [None, None]
        pair[attacker] = a
        pair[d] = o
        seq.append((f, pair))
    return seq, c, max(att_end, def_end)


class Base(unittest.TestCase):
    def run_frames(self, seq, human_slot=0, tracker=None):
        tracker = tracker or Tracker(SID)
        states, events = [], []
        for f, pair in seq:
            state = build_state(pair, human_slot, f, SID)
            self.assertIsNotNone(state)
            events.extend(tracker.step(state))
            states.append(state)
        self.assert_valid(states, events)
        return tracker, states, events

    def assert_valid(self, states, events):
        for s in states:
            errors = [e.message for e in STATE_V.iter_errors(s)]
            self.assertEqual(errors, [], f"state frame {s['frame']}")
        for ev in events:
            errors = [e.message for e in EVENT_V.iter_errors(ev)]
            self.assertEqual(errors, [], f"event {ev}")

    def at(self, states, frame, round_=None):
        found = [s for s in states if s["frame"] == frame and (round_ is None or s["round"] == round_)]
        self.assertEqual(len(found), 1, f"state for frame {frame}")
        return found[0]

    def kinds(self, events):
        return [e["kind"] for e in events]

    def only(self, events, kind):
        found = [e for e in events if e["kind"] == kind]
        self.assertEqual(len(found), 1, f"{kind} in {self.kinds(events)}")
        return found[0]


class HealthDecodeTest(unittest.TestCase):
    def test_known_value(self):
        self.assertEqual(decode_health(0xABCE343D, 0xBD20A1539B61342F), 175)

    def test_top_nibble_flip_rejected(self):
        for bit in range(28, 32):
            self.assertIsNone(decode_health(0xABCE343D ^ (1 << bit), 0xBD20A1539B61342F), hex(bit))

    def test_rotl64(self):
        self.assertEqual(rotl64(1, 64), 1)
        self.assertEqual(rotl64(1 << 63, 1), 1)
        self.assertEqual(rotl64(0x0123456789ABCDEF, 4), 0x123456789ABCDEF0)


class BuildTest(Base):
    def test_idle_player_fields(self):
        p = build_player(0, idle(0, 5))
        self.assertEqual(p["hit_level"], "none")
        self.assertEqual(p["being_thrown"], "none")
        self.assertFalse(p["throw_escaped"])
        self.assertEqual(p["heat_gauge"], 0.0)
        self.assertEqual(p["dir_held"], "n")
        self.assertEqual(p["buttons_held"], [])
        self.assertEqual(p["buttons_pressed"], [])
        self.assertTrue(p["free_movement"])
        self.assertEqual(p["frames_until_actionable"], 0)
        self.assertEqual((p["x"], p["y"], p["z"]), (-6000.0, 1040.0, -1000.0))

    def test_missing_health_returns_none(self):
        self.assertIsNone(build_state([idle(0), idle(1, health=None)], 0, 10, SID))
        self.assertIsNone(build_state([idle(0, max_health=None), idle(1)], 0, 10, SID))

    def test_state_shape(self):
        s = build_state([idle(0, 10), idle(1, 10)], 0, 10, SID)
        self.assertEqual(s["t"], "state")
        self.assertEqual(s["frame"], 10)
        self.assertEqual(s["human_slot"], 0)
        self.assertEqual([p["slot"] for p in s["players"]], [0, 1])
        self.assertEqual([p["character"] for p in s["players"]], ["devil_jin", "kazuya"])
        self.assert_valid([s], [])


class DerivedTest(Base):
    def test_distance_and_bearing(self):
        for human, bearing in ((0, 0.0), (1, 180.0)):
            s = build_state([idle(0), idle(1)], human, 0, SID)
            self.assertEqual(s["derived"]["distance_mm"], 2000.0)
            self.assertEqual(s["derived"]["distance_bucket"], "mid")
            self.assertEqual(s["derived"]["bearing_deg"], bearing)

    def test_timer(self):
        players = [build_player(0, idle(0)), build_player(1, idle(1))]
        self.assertEqual(derive(players, 0, 0)["timer_s"], 60.0)
        self.assertEqual(derive(players, 0, 90)["timer_s"], 58.5)
        self.assertEqual(derive(players, 0, 600)["timer_s"], 50.0)
        self.assertEqual(derive(players, 0, 3600)["timer_s"], 0.0)
        self.assertEqual(derive(players, 0, 5000)["timer_s"], 0.0)

    def test_advantage_formula(self):
        att = {"move_total": 27, "frame_in_move": 12}
        dfn = {"move_total": 18, "frame_in_move": 2}
        self.assertEqual(advantage(att, dfn), 1)


class FrameAdvantageTest(Base):
    def check_exchange(self, kind, expected_adv, damage=0, human_slot=0, **kw):
        seq, c, free_at = exchange(damage=damage, **kw)
        tracker, states, events = self.run_frames(seq, human_slot=human_slot)
        self.assertEqual(self.kinds(events), ["round_start", kind])
        ev = events[1]
        self.assertEqual(ev["frame"], c)
        self.assertEqual(ev["round"], 1)
        self.assertEqual(ev["frame_advantage"], expected_adv)
        self.assertEqual(ev["damage"], damage)
        self.assertEqual(ev["detail"]["read_frame"], c + 2)
        self.assertEqual(self.at(states, c)["derived"]["frame_advantage"], None)
        self.assertEqual(self.at(states, c + 1)["derived"]["frame_advantage"], None)
        human_adv = expected_adv if kw.get("attacker", 0) == human_slot else -expected_adv
        self.assertEqual(self.at(states, c + 2)["derived"]["frame_advantage"], human_adv)
        self.assertEqual(self.at(states, c + 5)["derived"]["frame_advantage"], human_adv)
        self.assertIsNone(self.at(states, free_at)["derived"]["frame_advantage"])
        self.assertEqual(self.at(states, free_at)["derived"]["situation"], "neutral")
        return ev, states, c

    def test_jab_blocked(self):
        ev, states, c = self.check_exchange("block", 1)
        self.assertEqual((ev["actor"], ev["target"]), (0, 1))
        self.assertEqual(ev["move_id"], JAB)
        self.assertEqual(ev["hit_level"], "high")
        d = ev["detail"]
        self.assertEqual((d["attacker_total"], d["attacker_frame"]), (27, 12))
        self.assertEqual((d["defender_move_id"], d["defender_total"], d["defender_frame"]), (0x604, 18, 2))
        self.assertEqual(self.at(states, c + 2)["derived"]["situation"], "pressure")

    def test_jab_blocked_human_defending(self):
        ev, states, c = self.check_exchange("block", 1, human_slot=1)
        self.assertEqual((ev["actor"], ev["target"]), (0, 1))
        self.assertEqual(self.at(states, c + 2)["derived"]["frame_advantage"], -1)
        self.assertEqual(self.at(states, c + 2)["derived"]["situation"], "defense")

    def test_jab_blocked_attacker_slot1(self):
        ev, states, c = self.check_exchange("block", 1, attacker=1, human_slot=1)
        self.assertEqual((ev["actor"], ev["target"]), (1, 0))

    def test_jab_normal_hit(self):
        ev, states, c = self.check_exchange("hit", 8, damage=5, reaction=12, def_move=0x600, def_total=25)
        self.assertEqual(ev["detail"]["reaction"], 12)
        self.assertEqual(self.at(states, c + 2)["players"][1]["health"], 185)

    def test_df1_blocked(self):
        ev, states, c = self.check_exchange("block", -6, move=DF1, total=38, connect_at=13, level_code=MID,
                                            level="mid", def_move=0x720, def_total=19)
        self.assertEqual(ev["move_id"], DF1)
        self.assertEqual(ev["hit_level"], "mid")
        d = ev["detail"]
        self.assertEqual(d["attacker_total"] - (d["attacker_frame"] - 2), 25)
        self.assertEqual(d["defender_total"], 19)
        self.assertEqual(self.at(states, c + 2)["derived"]["situation"], "defense")

    def test_counter_hit(self):
        ev, states, c = self.check_exchange("counter_hit", 18, damage=7, reaction=10, def_move=0x600, def_total=35)
        self.assertEqual(self.at(states, c + 2)["derived"]["situation"], "punish_window")

    def test_punish_window_threshold(self):
        ev, states, c = self.check_exchange("hit", 10, reaction=12, def_move=0x600, def_total=27)
        self.assertEqual(self.at(states, c + 2)["derived"]["situation"], "punish_window")
        ev, states, c = self.check_exchange("hit", 9, reaction=12, def_move=0x600, def_total=26)
        self.assertEqual(self.at(states, c + 2)["derived"]["situation"], "pressure")


def string_frames(second_level_code=HIGH, second_level="high", second_active=15):
    seq = []
    for f in range(97, 150):
        a, d = idle(0, f), idle(1, f)
        if 100 <= f < 110:
            a.update(move_id=0x644, frame_in_move=f - 99, move_total=27, free_movement=0, hit_level=HIGH,
                     hit_level_name="high", first_active=10, last_active=10)
        elif 110 <= f < 144:
            a.update(move_id=0x605, frame_in_move=f - 109, move_total=34, free_movement=0, hit_level=second_level_code,
                     hit_level_name=second_level, first_active=second_active, last_active=second_active)
        if f == 109:
            d.update(move_id=0x5C6, frame_in_move=8, move_total=22, hit_reaction=1)
        elif 110 <= f < 125:
            d.update(move_id=0x604, frame_in_move=f - 109, move_total=18, free_movement=0, hit_reaction=1)
        elif 125 <= f < 143:
            d.update(move_id=0x718, frame_in_move=f - 124, move_total=18, free_movement=0, hit_reaction=1)
        seq.append((f, [a, d]))
    return seq


class LyingTest(unittest.TestCase):
    def player(self, **overrides):
        return build_player(1, dict(idle(1, 0), **overrides))

    def test_lying_loop_is_ready(self):
        self.assertTrue(lying(self.player(status=0x6084, move_id=0x8007, move_total=60)))
        self.assertTrue(lying(self.player(status=0x6A84, move_id=0x800A, move_total=60)))

    def test_landing_throw_and_standing_are_not(self):
        self.assertFalse(lying(self.player(status=0x6084, move_id=0x8006, move_total=1)))
        self.assertFalse(lying(self.player(status=0x6084, move_id=0x7E0, move_total=60, being_thrown=0xE000001F)))
        self.assertFalse(lying(self.player(move_id=0x8001, move_total=88)))
        self.assertFalse(lying(self.player(status=0x6084, move_id=0x0092, move_total=5)))


def round_frames(frames, healths=(190, 190), start=0):
    seq = []
    for f in range(start, start + frames):
        a, d = idle(0, f, health=healths[0]), idle(1, f, health=healths[1])
        seq.append((f, [a, d]))
    return seq


def ko_frames(winner, start=0, frames=20):
    seq = round_frames(frames, start=start)
    loser = 1 - winner
    for f, pair in seq[frames // 2:]:
        pair[loser]["health"] = 0
    return seq


def command_throw_frames(landed=False, escaped=False):
    seq = []
    for f in range(97, 200):
        a, d = idle(0, f), idle(1, f)
        if 100 <= f < 130:
            a.update(move_id=0x895, frame_in_move=f - 99, move_total=60, free_movement=0)
            d.update(move_id=0x896, frame_in_move=f - 99, move_total=60, free_movement=0, status=0x6084)
            if f < 103:
                d.update(being_thrown=0xD000001C)
            if escaped and 102 <= f < 103:
                d.update(throw_escape_flags=0x800)
            if landed and f >= 120:
                d.update(health=155)
        elif f >= 130 and landed:
            d.update(health=155, move_id=0x8007, move_total=60, free_movement=0, status=0x6084, basic_state=12)
        seq.append((f, [a, d]))
    return seq


class CommandThrowBreakTest(Base):
    def test_break_without_escape_flag_counts_when_no_damage(self):
        _, _, events = self.run_frames(command_throw_frames())
        brk = self.only(events, "throw_break")
        self.assertEqual(brk["frame"], 130)
        self.assertEqual(brk["actor"], 1)
        self.assertEqual(brk["move_id"], 0x895)
        self.assertEqual(brk["detail"], {"input": "press_1", "evidence": "no_damage", "connect_frame": 100})

    def test_escape_flag_break_is_not_double_counted(self):
        _, _, events = self.run_frames(command_throw_frames(escaped=True))
        brk = self.only(events, "throw_break")
        self.assertEqual(brk["frame"], 102)
        self.assertEqual(brk["detail"]["evidence"], "escape_flag")

    def test_landed_throw_is_not_a_break(self):
        _, _, events = self.run_frames(command_throw_frames(landed=True))
        self.assertEqual([e for e in events if e["kind"] == "throw_break"], [])


class TimeoutTest(Base):
    def test_versus_counter_reset_without_ko_is_a_timeout(self):
        tracker = Tracker(SID, timeouts=True, rounds_to_win=3)
        _, _, events = self.run_frames(round_frames(30, (10, 106)) + round_frames(10), tracker=tracker)
        end = self.only(events, "round_end")
        self.assertEqual(end["detail"], {"reason": "time", "winner": 1, "match_over": False})
        self.assertEqual(end["frame"], 29)
        self.assertEqual(tracker.rounds[0]["winner"], 1)
        self.assertEqual(tracker.wins[1], 1)

    def test_equal_health_timeout_is_a_draw(self):
        tracker = Tracker(SID, timeouts=True)
        _, _, events = self.run_frames(round_frames(30, (90, 90)) + round_frames(10), tracker=tracker)
        self.assertEqual(self.only(events, "round_end")["detail"], {"reason": "time", "winner": None, "match_over": False})

    def test_practice_reset_is_not_a_timeout(self):
        _, _, events = self.run_frames(round_frames(30, (10, 106)) + round_frames(10))
        self.assertEqual(self.only(events, "round_end")["detail"], {"reason": "counter_reset", "winner": None, "match_over": False})

    def test_match_over_after_rounds_to_win(self):
        tracker = Tracker(SID, timeouts=True, rounds_to_win=3)
        seq = ko_frames(0) + ko_frames(0) + round_frames(30, (10, 106)) + ko_frames(0)
        self.assertFalse(tracker.match_over)
        _, _, events = self.run_frames(seq, tracker=tracker)
        self.assertEqual([r["winner"] for r in tracker.rounds], [0, 0, 1, 0])
        self.assertTrue(tracker.match_over)
        self.assertEqual(dict(tracker.wins), {0: 3, 1: 1})
        ends = [e for e in events if e["kind"] == "round_end"]
        self.assertEqual([e["detail"]["match_over"] for e in ends], [False, False, False, True])

    def test_stop_marks_the_match_over(self):
        tracker = Tracker(SID, timeouts=True, rounds_to_win=3)
        self.run_frames(ko_frames(0) + idle_frames(range(0, 4)), tracker=tracker)
        fin = tracker.finish()
        self.assertEqual(fin[0]["detail"], {"reason": "stop", "winner": None, "match_over": True})

    def test_practice_never_ends_the_match(self):
        tracker = Tracker(SID)
        self.run_frames(ko_frames(0) + ko_frames(0) + ko_frames(0) + ko_frames(0), tracker=tracker)
        self.assertFalse(tracker.match_over)


class StringTest(Base):
    def test_continued_string_has_no_advantage_and_second_block_counts(self):
        _, states, events = self.run_frames(string_frames())
        blocks = [e for e in events if e["kind"] == "block"]
        self.assertEqual([e["frame"] for e in blocks], [109, 125])
        self.assertIsNone(blocks[0]["frame_advantage"])
        self.assertTrue(blocks[0]["detail"]["string_continued"])
        self.assertEqual(blocks[1]["move_id"], 0x605)
        self.assertEqual(blocks[1]["frame_advantage"], -1)
        self.assertFalse(blocks[1]["detail"]["string_continued"])
        self.assertIsNone(self.at(states, 111)["derived"]["frame_advantage"])

    def test_reaction_change_without_an_active_attack_is_not_a_hit(self):
        _, _, events = self.run_frames(string_frames(NONE_CODE, "none", 0))
        blocks = [e for e in events if e["kind"] == "block"]
        self.assertEqual([e["frame"] for e in blocks], [109])
        self.assertIsNotNone(blocks[0]["frame_advantage"])
        self.assertFalse(blocks[0]["detail"]["string_continued"])

    def test_reaction_change_outside_active_frames_is_not_a_hit(self):
        _, _, events = self.run_frames(string_frames(second_active=5))
        self.assertEqual([e["frame"] for e in events if e["kind"] == "block"], [109])


class EventTest(Base):
    def test_round_start_first_frame(self):
        tracker, states, events = self.run_frames(idle_frames(range(100, 105)))
        self.assertEqual(self.kinds(events), ["round_start"])
        self.assertEqual(events[0]["frame"], 100)
        self.assertEqual(events[0]["round"], 1)
        self.assertTrue(all(s["round"] == 1 for s in states))
        self.assertTrue(all(s["derived"]["situation"] == "neutral" for s in states))
        self.assertTrue(all(s["derived"]["frame_advantage"] is None for s in states))

    def throw_seq(self, escape_at=None):
        seq = []
        for f in range(100, 112):
            a, d = idle(0, f), idle(1, f)
            if f >= 103:
                a.update(move_id=0x700, frame_in_move=f - 102, move_total=60, free_movement=0,
                         hit_level=THROW_LEVEL, hit_level_name="throw")
            if f >= 105:
                d.update(move_id=0x710, frame_in_move=f - 104, move_total=60, free_movement=0,
                         being_thrown=0xE000001F)
            if escape_at is not None and f >= escape_at:
                d["throw_escape_flags"] = 0x800
            seq.append((f, [a, d]))
        return seq

    def test_throw(self):
        tracker, states, events = self.run_frames(self.throw_seq())
        self.assertEqual(self.kinds(events), ["round_start", "throw"])
        ev = events[1]
        self.assertEqual(ev["frame"], 105)
        self.assertEqual((ev["actor"], ev["target"]), (0, 1))
        self.assertEqual(ev["move_id"], 0x700)
        self.assertEqual(ev["hit_level"], "throw")
        self.assertEqual(ev["detail"]["break"], "press_2")
        self.assertEqual(self.at(states, 105)["derived"]["situation"], "throw")
        self.assertEqual(self.at(states, 104)["derived"]["situation"], "neutral")

    def test_throw_break(self):
        tracker, states, events = self.run_frames(self.throw_seq(escape_at=108))
        self.assertEqual(self.kinds(events), ["round_start", "throw", "throw_break"])
        ev = events[2]
        self.assertEqual(ev["frame"], 108)
        self.assertEqual((ev["actor"], ev["target"]), (1, 0))
        self.assertTrue(self.at(states, 108)["players"][1]["throw_escaped"])

    def test_knockdown(self):
        seq = idle_frames(range(100, 103))
        for f in range(103, 108):
            seq.append((f, [idle(0, f), idle(1, f, status=0x1942 | 0x80, free_movement=0)]))
        tracker, states, events = self.run_frames(seq)
        self.assertEqual(self.kinds(events), ["round_start", "knockdown"])
        ev = events[1]
        self.assertEqual(ev["frame"], 103)
        self.assertEqual((ev["actor"], ev["target"]), (0, 1))
        self.assertEqual(ev["detail"]["cause"], "hit")
        self.assertEqual(self.at(states, 103)["derived"]["situation"], "knockdown")

    def test_side_switch(self):
        seq = idle_frames(range(100, 103))
        for f in range(103, 106):
            seq.append((f, [idle(0, f, side=1, position=(-6000.0, 1040.0, 1000.0)),
                            idle(1, f, side=0, position=(-6000.0, 1040.0, -1000.0))]))
        tracker, states, events = self.run_frames(seq)
        self.assertEqual(self.kinds(events), ["round_start", "side_switch"])
        self.assertEqual(events[1]["frame"], 103)
        self.assertEqual(events[1]["detail"]["sides"], [1, 0])

    def test_whiff(self):
        seq = []
        for f in range(97, 132):
            a = idle(0, f)
            if 100 <= f < 127:
                k = f - 99
                a.update(move_id=JAB, frame_in_move=k, move_total=27, free_movement=0)
                if 8 <= k <= 12:
                    a.update(hit_level=HIGH, hit_level_name="high")
            seq.append((f, [a, idle(1, f)]))
        tracker, states, events = self.run_frames(seq)
        self.assertEqual(self.kinds(events), ["round_start", "whiff"])
        ev = events[1]
        self.assertEqual(ev["actor"], 0)
        self.assertEqual(ev["move_id"], JAB)
        self.assertEqual(ev["hit_level"], "high")
        self.assertEqual(ev["frame"], 127)
        self.assertEqual(ev["detail"]["start_frame"], 107)

    def test_no_whiff_without_hit_level(self):
        seq = []
        for f in range(97, 120):
            a = idle(0, f)
            if 100 <= f < 115:
                a.update(move_id=0x900, frame_in_move=f - 99, move_total=15, free_movement=0)
            seq.append((f, [a, idle(1, f)]))
        tracker, states, events = self.run_frames(seq)
        self.assertEqual(self.kinds(events), ["round_start"])

    def test_blocked_jab_is_not_whiff(self):
        seq, c, free_at = exchange()
        tracker, states, events = self.run_frames(seq)
        self.assertNotIn("whiff", self.kinds(events))

    def test_counter_reset(self):
        seq = idle_frames(range(100, 111)) + idle_frames(range(0, 5))
        tracker, states, events = self.run_frames(seq)
        self.assertEqual(self.kinds(events), ["round_start", "round_end", "round_start"])
        end, start = events[1], events[2]
        self.assertEqual(end["round"], 1)
        self.assertEqual(end["frame"], 110)
        self.assertIsNone(end["detail"]["winner"])
        self.assertEqual(end["detail"]["reason"], "counter_reset")
        self.assertEqual(start["round"], 2)
        self.assertEqual(start["frame"], 0)
        self.assertEqual([s["round"] for s in states[:11]], [1] * 11)
        self.assertEqual([s["round"] for s in states[11:]], [2] * 5)
        self.assertEqual(tracker.rounds, [{"round": 1, "winner": None, "start_frame": 100, "end_frame": 110}])
        fin = tracker.finish()
        self.assertEqual(self.kinds(fin), ["round_end"])
        self.assertEqual(fin[0]["round"], 2)
        self.assertEqual(fin[0]["frame"], 4)
        self.assertEqual(fin[0]["detail"]["reason"], "stop")
        self.assertIsNone(fin[0]["detail"]["winner"])
        self.assert_valid([], fin)
        self.assertEqual(len(tracker.rounds), 2)
        self.assertEqual(tracker.finish(), [])

    def test_ko(self):
        seq = idle_frames(range(100, 103))
        for f in range(103, 108):
            seq.append((f, [idle(0, f), idle(1, f, health=0)]))
        tracker, states, events = self.run_frames(seq)
        self.assertEqual(self.kinds(events), ["round_start", "round_end"])
        ev = events[1]
        self.assertEqual(ev["frame"], 103)
        self.assertEqual(ev["round"], 1)
        self.assertEqual(ev["detail"]["winner"], 0)
        self.assertEqual(ev["detail"]["reason"], "ko")
        self.assertEqual(self.at(states, 102)["derived"]["situation"], "neutral")
        for f in range(103, 108):
            self.assertEqual(self.at(states, f)["derived"]["situation"], "round_over")
        self.assertEqual(tracker.rounds, [{"round": 1, "winner": 0, "start_frame": 100, "end_frame": 103}])
        self.assertEqual(tracker.finish(), [])

    def test_ko_slot0_then_reset(self):
        seq = idle_frames(range(100, 103))
        for f in range(103, 106):
            seq.append((f, [idle(0, f, health=0), idle(1, f)]))
        seq += idle_frames(range(0, 3))
        tracker, states, events = self.run_frames(seq)
        self.assertEqual(self.kinds(events), ["round_start", "round_end", "round_start"])
        self.assertEqual(events[1]["detail"]["winner"], 1)
        self.assertEqual(events[2]["round"], 2)
        self.assertEqual(self.at(states, 0)["derived"]["situation"], "neutral")
        self.assertEqual(self.at(states, 0)["round"], 2)
        self.assertEqual([r["winner"] for r in tracker.rounds], [1])

    def test_finish_without_ko(self):
        tracker, states, events = self.run_frames(idle_frames(range(100, 104)))
        fin = tracker.finish()
        self.assertEqual(self.kinds(fin), ["round_end"])
        self.assertEqual(fin[0]["frame"], 103)
        self.assertEqual(fin[0]["detail"], {"reason": "stop", "winner": None, "match_over": True})
        self.assert_valid([], fin)

    def test_finish_before_any_frame(self):
        self.assertEqual(Tracker(SID).finish(), [])


class SessionTest(Base):
    def test_session_id(self):
        self.assertEqual(session_id(datetime(2026, 10, 17, 13, 5, 0), "sahil", "devil_jin", "kazuya"),
                         "2026-10-17T13-05-00_sahil_djin_vs_kaz")

    def meta(self):
        return session_meta(SID, datetime(2026, 10, 17, 13, 5, 0), "sahil", 0, "devil_jin", "kazuya", 3,
                            "practice", "3.02.02")

    def test_session_meta_valid(self):
        meta = self.meta()
        self.assertEqual(meta["started_at"], "2026-10-17T13:05:00Z")
        self.assertEqual([e.message for e in SESSION_V.iter_errors(meta)], [])

    def test_result_text(self):
        self.assertEqual(result_text([], 0), "")
        self.assertEqual(result_text([{"winner": None}], 0), "")
        self.assertEqual(result_text([{"winner": 0}, {"winner": 1}, {"winner": 0}], 0), "win 2-1")
        self.assertEqual(result_text([{"winner": 0}, {"winner": 1}, {"winner": 0}], 1), "loss 1-2")
        self.assertEqual(result_text([{"winner": 0}, {"winner": 1}], 0), "draw 1-1")


class RecorderTest(Base):
    def test_recording_order_and_close(self):
        seq, c, free_at = exchange()
        seq += idle_frames(range(0, 4))
        meta = session_meta(SID, datetime(2026, 10, 17, 13, 5, 0), "sahil", 0, "devil_jin", "kazuya", 3,
                            "practice", "3.02.02")
        with tempfile.TemporaryDirectory() as tmp:
            rec = Recorder(meta, root=tmp)
            rec_path = Path(tmp) / "recordings" / f"{SID}.jsonl"
            sess_path = Path(tmp) / "sessions" / f"{SID}.json"
            self.assertTrue(rec_path.exists())
            self.assertTrue(sess_path.exists())
            tracker = Tracker(SID)
            for f, pair in seq:
                state = build_state(pair, 0, f, SID)
                evs = tracker.step(state)
                rec.state(state)
                rec.events(evs)
                rec.tick()
            fin = tracker.finish()
            rec.events(fin)
            rec.close(tracker.rounds, "2026-10-17T13:06:00Z", result_text(tracker.rounds, 0))
            lines = rec_path.read_text(encoding="utf-8").splitlines()
            records = [json.loads(line) for line in lines]
            session = json.loads(sess_path.read_text(encoding="utf-8"))
        self.assertEqual(len(records), len(seq) + 5)
        self.assert_valid([r for r in records if r["t"] == "state"], [r for r in records if r["t"] == "event"])
        keys = [(r["round"], r["frame"]) for r in records]
        self.assertEqual(keys, sorted(keys))

        def index(pred):
            found = [i for i, r in enumerate(records) if pred(r)]
            self.assertEqual(len(found), 1)
            return found[0]

        block = index(lambda r: r.get("kind") == "block")
        state_c = index(lambda r: r["t"] == "state" and r["round"] == 1 and r["frame"] == c)
        state_c1 = index(lambda r: r["t"] == "state" and r["round"] == 1 and r["frame"] == c + 1)
        self.assertLess(state_c, block)
        self.assertLess(block, state_c1)
        self.assertEqual(records[block]["frame_advantage"], 1)
        self.assertEqual(records[0]["kind"], "round_start")
        first_r2 = index(lambda r: r.get("kind") == "round_start" and r["round"] == 2)
        state_r2 = index(lambda r: r["t"] == "state" and r["round"] == 2 and r["frame"] == 0)
        self.assertLess(first_r2, state_r2)
        r1_end = index(lambda r: r.get("kind") == "round_end" and r["round"] == 1)
        self.assertLess(r1_end, first_r2)
        self.assertEqual(records[-1]["kind"], "round_end")
        self.assertEqual(records[-1]["detail"]["reason"], "stop")
        self.assertEqual(session["ended_at"], "2026-10-17T13:06:00Z")
        self.assertEqual([r["round"] for r in session["rounds"]], [1, 2])
        self.assertEqual(session["recording"], rec_path.as_posix())
        self.assertEqual(session["result"], "")
        self.assertEqual([e.message for e in SESSION_V.iter_errors(session)], [])

    def test_round_start_sorts_before_state(self):
        meta = session_meta(SID, datetime(2026, 10, 17, 13, 5, 0), "sahil", 0, "devil_jin", "kazuya", 3,
                            "practice", "3.02.02")
        with tempfile.TemporaryDirectory() as tmp:
            rec = Recorder(meta, root=tmp)
            tracker = Tracker(SID)
            state = build_state([idle(0, 50), idle(1, 50)], 0, 50, SID)
            evs = tracker.step(state)
            rec.state(state)
            rec.events(evs)
            rec.close(tracker.rounds, "2026-10-17T13:06:00Z")
            records = [json.loads(line) for line in
                       (Path(tmp) / "recordings" / f"{SID}.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r.get("kind", r["t"]) for r in records], ["round_start", "state"])


if __name__ == "__main__":
    unittest.main()
