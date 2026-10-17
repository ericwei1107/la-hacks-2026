import random
import unittest
from pathlib import Path

from game.difficulty import Difficulty
from game.notation import NEUTRAL
from game.reflex import BREAKS, Reflex, load_punishers
from game.replay_reflex import replay
from game.sequencer import Sequencer
from game.state import Tracker, build_state
from game.summarize import load_jsonl
from game.tests.test_pad import fake_pad
from game.tests.test_state import SID, exchange, idle

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "samples" / "practice_djin_vs_kaz.jsonl"
LATENCY = 2
LEVELS = {"high": 0xA000050F, "mid": 0x8000020A, "low": 0x20000112, "special_low": 0x60000402, "throw": 0x60000A1D}
THROWS = {"press_1": 0xD000001C, "press_2": 0xE000001F, "press_12": 0xF000001E}
BREAK_BUTTONS = {"press_1": {"X"}, "press_2": {"Y"}, "press_12": {"X", "Y"}}
BACK = {0: "DPAD_LEFT", 1: "DPAD_RIGHT"}
FIRST_PRESS = {"1,1,2": {"X"}, "2": {"Y"}, "df+4": {"DPAD_DOWN", "DPAD_LEFT", "B"},
               "df+2": {"DPAD_DOWN", "DPAD_LEFT", "Y"}, "df+1": {"DPAD_DOWN", "DPAD_LEFT", "X"},
               "ws+1": {"X"}, "ws+2": {"Y"}}
ATTACK = 0x6A6
STATUS = 0x1942
DOWNED = 0x80
JUGGLED = 0x400
PUNISHERS, _ = load_punishers("kazuya")


def exact(delay=0, **knobs):
    values = {"reaction_delay_frames": delay, "frame_perfect_chance": 0.0, "execution_error": 0.0, "punish_accuracy": 1.0}
    values.update(knobs)
    return Difficulty.preset(5).with_knobs(**values)


class FixedDelay:
    execution_error = 0.0

    def __init__(self, delay, accurate=True):
        self.delay = delay
        self.hit = accurate

    def reaction(self, rng):
        return self.delay

    def accurate(self, rng):
        return self.hit


def guard_buttons(guard, side):
    return {BACK[side]} | ({"DPAD_DOWN"} if guard == "db" else set())


class Rig:
    def __init__(self, difficulty=None, seed=0, human_slot=0, rng=None):
        self.pad, self.device = fake_pad()
        self.difficulty = difficulty or exact()
        self.rng = rng or random.Random(seed)
        self.seq = Sequencer(self.pad, LATENCY, self.difficulty, self.rng)
        self.reflex = Reflex(self.seq, self.difficulty, LATENCY, PUNISHERS, self.rng)
        self.tracker = Tracker(SID)
        self.human_slot = human_slot
        self.pressed = {}
        self.records = []
        self.events = []
        self.states = {}
        self.submitted = []
        submit = self.seq.submit

        def tracked(*args, **kwargs):
            move = submit(*args, **kwargs)
            self.submitted.append(move)
            return move

        self.seq.submit = tracked

    def step(self, f, pair):
        state = build_state(pair, self.human_slot, f, SID)
        evs = self.tracker.step(state)
        recs = self.reflex.step(state, evs)
        self.seq.on_frame(f, state["players"][1 - self.human_slot], self.reflex.live(state))
        self.pressed[f] = set(self.device.pressed)
        self.states[f] = state
        self.records.extend(recs)
        self.events.extend(evs)
        return recs

    def run(self, frames):
        for f, pair in frames:
            self.step(f, pair)
        return self

    def kind(self, kind):
        return [r for r in self.records if r["reflex"]["kind"] == kind]

    def moves(self, reflex):
        return [m for m in self.submitted if m.tag.get("reflex") == reflex]


def attack(attacker, level, start=100, length=20, lead=3, tail=8, defender=None):
    frames = []
    for f in range(start - lead, start + length + tail):
        pair = [idle(0, f), idle(1, f)]
        if start <= f < start + length:
            pair[attacker].update(move_id=ATTACK, frame_in_move=f - start + 1, move_total=length, free_movement=0,
                                  hit_level=LEVELS[level], hit_level_name=level)
        if defender:
            pair[1 - attacker].update(defender)
        frames.append((f, pair))
    return frames


def punish_frames(advantage, reaction=1, level="mid"):
    return exchange(attacker=0, move=ATTACK, total=40, connect_at=10, level_code=LEVELS[level], level=level,
                    reaction=reaction, def_move=0x604, def_total=30 - advantage, tail=20)


def throw_frames(code, start=100, connect=105, end=130):
    frames = []
    for f in range(start, end):
        a, d = idle(0, f), idle(1, f)
        if f > start:
            a.update(move_id=0x7DF, frame_in_move=f - start, move_total=60, free_movement=0,
                     hit_level=LEVELS["throw"], hit_level_name="throw")
        if f >= connect:
            d.update(move_id=0x7E0, frame_in_move=f - connect + 1, move_total=60, free_movement=0,
                     being_thrown=THROWS[code])
        frames.append((f, [a, d]))
    return frames


def blocked_state(until=16, reaction=1, frame=200):
    pair = [idle(0, frame), idle(1, frame)]
    pair[1].update(move_id=0x604, frame_in_move=2, move_total=until + 2, free_movement=0, hit_reaction=reaction)
    state = build_state(pair, 0, frame, SID)
    Tracker(SID).step(state)
    return state


def block_event(advantage, reaction=1, frame=198):
    return {"t": "event", "session_id": SID, "frame": frame, "round": 1, "kind": "block", "actor": 0, "target": 1,
            "move_id": ATTACK, "hit_level": "mid", "frame_advantage": -advantage, "detail": {"reaction": reaction}}


def strongest(tiers, advantage, lateness):
    fits = [t["notation"] for t in tiers if t["startup"] <= advantage - lateness]
    return fits[-1] if fits else "none"


class BlockTest(unittest.TestCase):
    def check_block(self, level, guard, human_slot):
        attacker = human_slot
        bot_side = 1 - human_slot
        rig = Rig(exact(8), seed=3, human_slot=human_slot).run(attack(attacker, level))
        blocks = rig.kind("block")
        self.assertEqual(len(blocks), 1)
        rec = blocks[0]
        self.assertEqual(rec["chosen"], guard)
        self.assertEqual(rec["frame"], 100)
        self.assertEqual(rec["frame_asked"], 100)
        self.assertEqual(rec["options"], ["b", "db"])
        self.assertEqual(rec["reflex"]["hit_level"], level)
        at = 100 + max(0, rec["reflex"]["delay"] - LATENCY)
        self.assertEqual(rec["reflex"]["planned_frame"], at)
        self.assertGreater(at, 100)
        held = guard_buttons(guard, bot_side)
        for f in range(97, at):
            self.assertEqual(rig.pressed[f], set(), f"frame {f}")
        for f in range(at, 123):
            self.assertEqual(rig.pressed[f], held, f"frame {f}")
        for f in range(123, 128):
            self.assertEqual(rig.pressed[f], set(), f"frame {f}")

    def test_mid_and_high_hold_back(self):
        for level in ("mid", "high"):
            for human_slot in (0, 1):
                with self.subTest(level=level, human_slot=human_slot):
                    self.check_block(level, "b", human_slot)

    def test_lows_hold_down_back(self):
        for level in ("low", "special_low"):
            for human_slot in (0, 1):
                with self.subTest(level=level, human_slot=human_slot):
                    self.check_block(level, "db", human_slot)

    def test_back_direction_per_side(self):
        rig = Rig(exact(0)).run(attack(0, "mid"))
        self.assertEqual(rig.pressed[105], {"DPAD_RIGHT"})
        rig = Rig(exact(0), human_slot=1).run(attack(1, "mid"))
        self.assertEqual(rig.pressed[105], {"DPAD_LEFT"})

    def test_zero_delay_holds_on_first_frame(self):
        rig = Rig(exact(0)).run(attack(0, "low"))
        self.assertEqual(rig.kind("block")[0]["reflex"]["planned_frame"], 100)
        self.assertEqual(rig.pressed[99], set())
        self.assertEqual(rig.pressed[100], {"DPAD_DOWN", "DPAD_RIGHT"})

    def test_same_guard_already_held_is_immediate(self):
        frames = attack(0, "mid", start=100, length=10, tail=0) + attack(0, "high", start=111, length=10, lead=1)
        rig = Rig(exact(8), seed=1).run(frames)
        blocks = rig.kind("block")
        self.assertEqual([b["frame"] for b in blocks], [100, 111])
        self.assertEqual(blocks[1]["reflex"]["delay"], 0)
        self.assertEqual(rig.pressed[111], {"DPAD_RIGHT"})

    def test_counter_reset_clears_guard(self):
        frames = attack(0, "mid", start=300, length=10, tail=0) + attack(0, "mid", start=20, length=20, lead=1)
        rig = Rig(FixedDelay(8)).run(frames)
        blocks = rig.kind("block")
        self.assertEqual([b["frame"] for b in blocks], [300, 20])
        self.assertEqual(blocks[1]["reflex"]["delay"], 8)
        self.assertEqual(rig.pressed[25], set())
        self.assertEqual(rig.pressed[26], {"DPAD_RIGHT"})

    def test_throw_and_idle_are_not_threats(self):
        rig = Rig(exact(0)).run(attack(0, "throw"))
        self.assertEqual(rig.kind("block"), [])
        self.assertTrue(all(p == set() for p in rig.pressed.values()))


class IncapableTest(unittest.TestCase):
    def test_no_block_while_downed_or_juggled(self):
        for bit in (DOWNED, JUGGLED):
            with self.subTest(bit=hex(bit)):
                rig = Rig(exact(0)).run(attack(0, "mid", defender={"status": STATUS | bit, "free_movement": 0}))
                self.assertEqual(rig.kind("block"), [])
                self.assertEqual(rig.records, [])
                self.assertTrue(all(p == set() for p in rig.pressed.values()))
                self.assertEqual(rig.seq.background, NEUTRAL)

    def test_no_block_while_being_thrown(self):
        rig = Rig(exact(0, punish_accuracy=0.0)).run(
            attack(0, "mid", defender={"being_thrown": THROWS["press_2"], "free_movement": 0}))
        self.assertEqual(rig.kind("block"), [])
        breaks = rig.kind("throw_break")
        self.assertEqual(len(breaks), 1)
        self.assertEqual(breaks[0]["reflex"]["rolled_miss"], "skipped")
        self.assertTrue(all(p == set() for p in rig.pressed.values()))

    def test_downed_mid_hold_drops_guard(self):
        frames = attack(0, "mid", length=30)
        for f, pair in frames:
            if 110 <= f < 115:
                pair[1].update(status=STATUS | DOWNED, free_movement=0)
        rig = Rig(exact(0)).run(frames)
        self.assertEqual(rig.pressed[109], {"DPAD_RIGHT"})
        for f in range(110, 115):
            self.assertEqual(rig.pressed[f], set(), f"frame {f}")

    def test_attack_started_while_downed_is_blocked_after_getting_up(self):
        frames = attack(0, "low", length=30)
        for f, pair in frames:
            if f < 110:
                pair[1].update(status=STATUS | DOWNED, free_movement=0)
        rig = Rig(exact(0)).run(frames)
        self.assertEqual(rig.pressed[109], set())
        self.assertEqual(len(rig.kind("block")), 1)
        self.assertEqual(rig.pressed[115], {"DPAD_DOWN", "DPAD_RIGHT"})


class PunishStandingTest(unittest.TestCase):
    def run_punish(self, advantage, reaction=1, level="mid", difficulty=None, seed=0):
        frames, c, _ = punish_frames(advantage, reaction, level)
        rig = Rig(difficulty or exact(0, frame_perfect_chance=1.0), seed=seed).run(frames)
        block = [e for e in rig.events if e["kind"] == "block"]
        self.assertEqual(len(block), 1)
        self.assertEqual(block[0]["frame_advantage"], -advantage)
        self.assertEqual(block[0]["detail"]["reaction"], reaction)
        return rig, c

    def test_tiers(self):
        for advantage, notation in ((10, "1,1,2"), (11, "1,1,2"), (12, "2"), (13, "df+4"), (14, "df+2"), (15, "df+1"),
                                    (20, "df+1")):
            with self.subTest(advantage=advantage):
                rig, c = self.run_punish(advantage)
                recs = rig.kind("punish")
                self.assertEqual(len(recs), 1)
                rec = recs[0]
                r = rec["reflex"]
                self.assertEqual(rec["chosen"], notation)
                self.assertEqual(rec["frame"], c + 2)
                self.assertEqual(rec["frame_asked"], c)
                self.assertEqual(rec["options"], [t["notation"] for t in PUNISHERS["standing"]] + ["none"])
                self.assertEqual(r["stance"], "standing")
                self.assertEqual(r["advantage"], advantage)
                self.assertEqual(r["delay"], 0)
                self.assertEqual(r["lateness"], 0)
                self.assertEqual(r["best"], notation)
                self.assertIsNone(r["rolled_miss"])
                self.assertEqual(r["blocked_move_id"], ATTACK)
                actionable = c + 30 - advantage
                self.assertEqual(r["actionable_frame"], actionable)
                self.assertEqual(r["planned_frame"], actionable - LATENCY)
                moves = rig.moves("punish")
                self.assertEqual(len(moves), 1)
                move = moves[0]
                self.assertEqual(move.notation, notation)
                self.assertTrue(move.prepress)
                self.assertFalse(move.force)
                self.assertEqual(move.lead, 0)
                self.assertEqual(move.queued_frame, c + 2)
                self.assertEqual(move.start_frame, actionable - LATENCY)
                self.assertEqual(rig.states[move.start_frame]["players"][1]["frames_until_actionable"], LATENCY)
                presses = [f for f, mask in rig.seq.applied if mask[1]]
                self.assertEqual(presses[0], actionable - LATENCY)
                self.assertEqual(rig.pressed[actionable - LATENCY], FIRST_PRESS[notation])
                self.assertEqual(rig.pressed[actionable - LATENCY - 1], {"DPAD_RIGHT"})

    def test_below_threshold_no_record(self):
        for advantage in (9, 5, 1):
            with self.subTest(advantage=advantage):
                rig, c = self.run_punish(advantage)
                self.assertEqual(rig.kind("punish"), [])
                self.assertEqual(rig.moves("punish"), [])
                self.assertFalse(any(mask[1] for _, mask in rig.seq.applied))

    def test_hit_events_ignored(self):
        rig = Rig(exact(0, frame_perfect_chance=1.0))
        state = blocked_state()
        ev = dict(block_event(12), kind="hit")
        self.assertEqual(rig.reflex.step(state, [ev]), [])
        ev = dict(block_event(12), target=0)
        self.assertEqual(rig.reflex.step(state, [ev]), [])
        self.assertEqual(rig.submitted, [])


class PunishCrouchingTest(unittest.TestCase):
    def test_ws_tiers(self):
        for advantage, notation in ((16, "ws+2"), (13, "ws+1"), (15, "ws+1"), (20, "ws+2")):
            with self.subTest(advantage=advantage):
                frames, c, _ = punish_frames(advantage, reaction=2, level="low")
                rig = Rig(exact(0, frame_perfect_chance=1.0)).run(frames)
                recs = rig.kind("punish")
                self.assertEqual(len(recs), 1)
                rec = recs[0]
                self.assertEqual(rec["chosen"], notation)
                self.assertEqual(rec["options"], ["ws+1", "ws+2", "none"])
                self.assertEqual(rec["reflex"]["stance"], "crouching")
                self.assertEqual(rec["reflex"]["lateness"], 0)
                actionable = c + 30 - advantage
                self.assertEqual(rec["reflex"]["planned_frame"], actionable - LATENCY - 1)
                move = rig.moves("punish")[0]
                self.assertEqual(move.lead, 1)
                self.assertEqual(move.frames[0], NEUTRAL)
                self.assertFalse(any(mask[0] == "d" for mask in move.frames))
                self.assertEqual(move.start_frame, actionable - LATENCY - 1)
                self.assertEqual(rig.pressed[move.start_frame - 1], {"DPAD_DOWN", "DPAD_RIGHT"})
                self.assertEqual(rig.pressed[move.start_frame], set())
                self.assertEqual(rig.pressed[move.start_frame + 1], FIRST_PRESS[notation])

    def test_ws_below_fastest(self):
        frames, c, _ = punish_frames(12, reaction=2, level="low")
        rig = Rig(exact(0, frame_perfect_chance=1.0)).run(frames)
        rec = rig.kind("punish")[0]
        self.assertEqual(rec["chosen"], "none")
        self.assertIsNone(rec["reflex"]["best"])
        self.assertIsNone(rec["reflex"]["planned_frame"])
        self.assertEqual(rig.moves("punish"), [])


class LatePunishTest(unittest.TestCase):
    def check(self, rec, advantage, lead=0):
        r = rec["reflex"]
        tiers = PUNISHERS[r["stance"]]
        earliest = max(rec["frame"], rec["frame_asked"] + max(0, r["delay"] - LATENCY))
        lateness = max(0, earliest - (r["actionable_frame"] - LATENCY - lead))
        self.assertEqual(rec["chosen"], strongest(tiers, advantage, lateness))
        self.assertEqual(r["best"] or "none", rec["chosen"])
        if rec["chosen"] != "none":
            self.assertEqual(r["lateness"], lateness)
            self.assertLessEqual(r["startup"], advantage - lateness)
            self.assertEqual(r["planned_frame"], max(earliest, r["actionable_frame"] - LATENCY - lead))
        else:
            self.assertIsNone(r["lateness"])
        return lateness

    def test_slow_reaction_skips(self):
        late = 0
        for seed in range(30):
            frames, c, _ = punish_frames(12)
            rig = Rig(exact(30), seed=seed).run(frames)
            rec = rig.kind("punish")[0]
            lateness = self.check(rec, 12)
            if lateness > 0:
                late += 1
                self.assertNotEqual(rec["chosen"], "2")
        self.assertGreaterEqual(late, 27)

    def test_moderate_reaction_downgrades(self):
        outcomes = {}
        for seed in range(60):
            frames, c, _ = punish_frames(12)
            rig = Rig(exact(19), seed=seed).run(frames)
            rec = rig.kind("punish")[0]
            lateness = self.check(rec, 12)
            outcomes.setdefault((rec["chosen"], lateness > 0), 0)
            outcomes[(rec["chosen"], lateness > 0)] += 1
            moves = rig.moves("punish")
            if rec["chosen"] == "none":
                self.assertEqual(moves, [])
            else:
                self.assertEqual(moves[0].start_frame, rec["reflex"]["planned_frame"])
        self.assertIn(("2", False), outcomes)
        self.assertIn(("1,1,2", True), outcomes)
        self.assertIn(("none", True), outcomes)

    def test_fixed_delay_lateness(self):
        for delay, chosen, lateness in ((0, "2", 0), (18, "2", 0), (19, "1,1,2", 1), (20, "1,1,2", 2), (21, "none", None),
                                        (40, "none", None)):
            with self.subTest(delay=delay):
                rig = Rig(FixedDelay(delay))
                rec = rig.reflex.step(blocked_state(until=16), [block_event(12)])[0]
                self.assertEqual(rec["reflex"]["delay"], delay)
                self.assertEqual(rec["chosen"], chosen)
                self.assertEqual(rec["reflex"]["lateness"], lateness)
                self.assertEqual(self.check(rec, 12), max(0, delay - 18))


class PunishAccuracyTest(unittest.TestCase):
    def trials(self, advantage, accuracy, n=400, seed=11):
        rig = Rig(exact(0, frame_perfect_chance=1.0, punish_accuracy=accuracy), seed=seed)
        state = blocked_state(until=16)
        recs = [rig.reflex.step(state, [block_event(advantage)])[0] for _ in range(n)]
        return rig, recs

    def test_zero_accuracy_splits_skip_and_too_slow(self):
        rig, recs = self.trials(12, 0.0)
        misses = [r["reflex"]["rolled_miss"] for r in recs]
        self.assertTrue(all(m in ("skipped", "too_slow") for m in misses))
        skipped = misses.count("skipped")
        self.assertTrue(0.4 <= skipped / len(recs) <= 0.6, skipped)
        for r in recs:
            self.assertEqual(r["reflex"]["best"], "2")
            if r["reflex"]["rolled_miss"] == "skipped":
                self.assertEqual(r["chosen"], "none")
                self.assertIsNone(r["reflex"]["planned_frame"])
            else:
                self.assertEqual(r["chosen"], "df+4")
                self.assertEqual(r["reflex"]["startup"], 13)
                self.assertGreater(r["reflex"]["startup"], r["reflex"]["advantage"])
        self.assertEqual(len(rig.submitted), misses.count("too_slow"))
        self.assertTrue(all(m.notation == "df+4" for m in rig.submitted))

    def test_zero_accuracy_without_slower_tier_always_skips(self):
        rig, recs = self.trials(15, 0.0, n=100)
        self.assertTrue(all(r["reflex"]["rolled_miss"] == "skipped" for r in recs))
        self.assertTrue(all(r["chosen"] == "none" for r in recs))
        self.assertEqual(rig.submitted, [])

    def test_full_accuracy_never_misses(self):
        rig, recs = self.trials(12, 1.0, n=200)
        self.assertTrue(all(r["reflex"]["rolled_miss"] is None for r in recs))
        self.assertTrue(all(r["chosen"] == "2" for r in recs))
        self.assertEqual(len(rig.submitted), 200)


class ThrowBreakTest(unittest.TestCase):
    def check_break(self, code, difficulty, seed=0):
        rig = Rig(difficulty, seed=seed).run(throw_frames(code))
        recs = rig.kind("throw_break")
        self.assertEqual(len(recs), 1)
        rec = recs[0]
        r = rec["reflex"]
        self.assertEqual(rec["frame"], 105)
        self.assertEqual(rec["chosen"], BREAKS[code])
        self.assertEqual(rec["options"], ["1", "2", "1+2", "none"])
        self.assertEqual(r["code"], code)
        self.assertIsNone(r["rolled_miss"])
        planned = r["planned_frame"]
        self.assertEqual(planned, 105 + max(0, min(r["delay"], 10) - LATENCY))
        self.assertLessEqual(planned, 105 + 10 - LATENCY)
        move = rig.moves("throw_break")[0]
        self.assertTrue(move.force)
        self.assertEqual(move.start_frame, planned)
        self.assertFalse(rig.states[planned]["players"][1]["free_movement"])
        for f in range(100, planned):
            self.assertEqual(rig.pressed[f], set(), f"frame {f}")
        for f in range(planned, planned + 3):
            self.assertEqual(rig.pressed[f], BREAK_BUTTONS[code], f"frame {f}")
        self.assertEqual(rig.pressed[planned + 3], set())
        self.assertEqual(rig.kind("block"), [])
        return rec

    def test_each_break(self):
        for code in THROWS:
            for delay in (0, 6):
                with self.subTest(code=code, delay=delay):
                    self.check_break(code, exact(delay), seed=4)

    def test_slow_reaction_still_in_window(self):
        for code in THROWS:
            for seed in range(5):
                with self.subTest(code=code, seed=seed):
                    rec = self.check_break(code, exact(30), seed=seed)
                    self.assertEqual(rec["reflex"]["planned_frame"], 105 + 10 - LATENCY)

    def test_zero_accuracy_skips(self):
        for code in THROWS:
            with self.subTest(code=code):
                rig = Rig(exact(6, punish_accuracy=0.0)).run(throw_frames(code))
                rec = rig.kind("throw_break")[0]
                self.assertEqual(rec["reflex"]["rolled_miss"], "skipped")
                self.assertEqual(rec["chosen"], "none")
                self.assertIsNone(rec["reflex"]["planned_frame"])
                self.assertEqual(rig.submitted, [])
                self.assertTrue(all(p == set() for p in rig.pressed.values()))

    def test_break_cancels_guard_and_queued_punish(self):
        rig = Rig(exact(0))
        rig.seq.hold("b")
        queued = rig.seq.submit("df+1", prepress=True, earliest=1000, reflex="punish")
        rig.reflex.guard = "b"
        rig.step(*throw_frames("press_1", connect=101)[0])
        self.assertEqual(rig.pressed[100], {"DPAD_RIGHT"})
        rig.run(throw_frames("press_1", connect=101)[1:])
        self.assertTrue(queued.cancelled)
        self.assertEqual(queued.done_frame, 101)
        self.assertEqual(rig.reflex.guard, "n")
        self.assertEqual(rig.kind("throw_break")[0]["chosen"], "1")
        self.assertEqual(rig.pressed[101], {"X"})
        self.assertEqual(rig.pressed[104], set())

    def test_only_on_transition(self):
        rig = Rig(exact(0)).run(throw_frames("press_2", end=200))
        self.assertEqual(len(rig.kind("throw_break")), 1)


class RecordShapeTest(unittest.TestCase):
    def records(self):
        recs = Rig(exact(4), seed=2).run(attack(0, "low")).records
        frames, c, _ = punish_frames(12)
        recs += Rig(exact(0, frame_perfect_chance=1.0)).run(frames).records
        recs += Rig(exact(6, punish_accuracy=0.0)).run(throw_frames("press_12")).records
        recs += Rig(exact(6)).run(throw_frames("press_1")).records
        return recs

    def test_contract_fields(self):
        recs = self.records()
        self.assertEqual({r["reflex"]["kind"] for r in recs}, {"block", "punish", "throw_break"})
        for rec in recs:
            with self.subTest(kind=rec["reflex"]["kind"], frame=rec["frame"]):
                self.assertEqual(rec["t"], "tactical")
                self.assertEqual(rec["session_id"], SID)
                self.assertEqual(rec["round"], 1)
                self.assertIsInstance(rec["frame"], int)
                self.assertIsInstance(rec["frame_asked"], int)
                self.assertLessEqual(rec["frame_asked"], rec["frame"])
                self.assertIsInstance(rec["options"], list)
                self.assertEqual(len(set(rec["options"])), len(rec["options"]))
                self.assertIn(rec["chosen"], rec["options"])
                self.assertEqual(set(rec["probabilities"]), set(rec["options"]))
                self.assertAlmostEqual(sum(rec["probabilities"].values()), 1.0)
                self.assertEqual(rec["probabilities"][rec["chosen"]], 1.0)
                self.assertEqual(rec["source"], "reflex")

    def test_decisions_log(self):
        rig = Rig(exact(0)).run(attack(0, "mid"))
        self.assertEqual(rig.reflex.decisions, rig.records)


class LiveTest(unittest.TestCase):
    def test_ko_releases_hold(self):
        frames = attack(0, "mid", length=30)
        for f, pair in frames:
            if f >= 110:
                pair[1]["health"] = 0
        rig = Rig(exact(0))
        for f, pair in frames:
            recs = rig.step(f, pair)
            if f >= 110:
                self.assertEqual(recs, [], f"frame {f}")
                self.assertEqual(rig.pressed[f], set(), f"frame {f}")
                self.assertFalse(rig.reflex.live(rig.states[f]))
        self.assertEqual(rig.pressed[109], {"DPAD_RIGHT"})
        self.assertEqual(rig.states[110]["derived"]["situation"], "round_over")
        self.assertEqual(rig.reflex.guard, "n")
        self.assertFalse(rig.seq.busy())
        self.assertEqual(rig.seq.background, NEUTRAL)

    def test_round_over_situation(self):
        rig = Rig(exact(0))
        state = blocked_state(until=16)
        state["derived"]["situation"] = "round_over"
        self.assertFalse(rig.reflex.live(state))
        self.assertEqual(rig.reflex.step(state, [block_event(12)]), [])
        self.assertEqual(rig.submitted, [])

    def test_any_health_zero(self):
        rig = Rig(exact(0))
        for slot in (0, 1):
            state = blocked_state(until=16)
            state["players"][slot]["health"] = 0
            self.assertFalse(rig.reflex.live(state))
            self.assertEqual(rig.reflex.step(state, [block_event(12)]), [])
        self.assertTrue(rig.reflex.live(blocked_state(until=16)))

    def test_not_live_cancels_queued_punish(self):
        frames, c, _ = punish_frames(12)
        rig = Rig(exact(0, frame_perfect_chance=1.0))
        for f, pair in frames:
            if f > c + 2:
                pair[0]["health"] = 0
            rig.step(f, pair)
        move = rig.moves("punish")[0]
        self.assertTrue(move.cancelled)
        self.assertIsNone(move.start_frame)
        self.assertFalse(any(mask[1] for _, mask in rig.seq.applied))
        self.assertEqual(rig.pressed[frames[-1][0]], set())


class ReplayHarnessTest(unittest.TestCase):
    def test_sample_recording(self):
        states = [r for r in load_jsonl(SAMPLE) if r.get("t") == "state"]
        self.assertGreater(len(states), 0)
        records, events, applied = replay(states, Difficulty.preset(5), seed=0)
        kinds = [r["reflex"]["kind"] for r in records]
        self.assertGreaterEqual(kinds.count("block"), 1)
        breaks = [r for r in records if r["reflex"]["kind"] == "throw_break"]
        self.assertEqual(len(breaks), 1)
        self.assertEqual(breaks[0]["chosen"], "2")
        self.assertEqual(breaks[0]["round"], 1)
        self.assertEqual(breaks[0]["frame"], 4697)
        self.assertEqual(breaks[0]["reflex"]["code"], "press_2")
        self.assertLessEqual(breaks[0]["reflex"]["planned_frame"], 4697 + 10 - LATENCY)
        self.assertTrue(any(mask[1] == ("2",) and frame >= 4697 for _, frame, mask in applied))
        self.assertTrue(all(r["source"] == "reflex" and r["chosen"] in r["options"] for r in records))

    def test_replay_is_deterministic(self):
        states = [r for r in load_jsonl(SAMPLE) if r.get("t") == "state"]
        first = replay(states, Difficulty.preset(3), seed=5)
        second = replay(states, Difficulty.preset(3), seed=5)
        self.assertEqual(first[0], second[0])
        self.assertEqual(first[2], second[2])


if __name__ == "__main__":
    unittest.main()
