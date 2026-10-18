import copy
import importlib.util
import json
import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from game.difficulty import Difficulty
from game.learning import (ACTIVE_N, ANY_KEY, FIXED_N, MINUS_KEY, PLUS_KEY, Bandit, Habits, Learning, Mastery, Predictor, forest,
                           learner_keys, not_broken_by)
from game.options import load_fallback, normalize_table
from game.replay_learn import run_learning
from game.state import build_state
from game.summarize import find_session, load_jsonl
from game.tests.test_state import SID, idle
from game.tests.test_tactical import TRig, frames, plus_five

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"
NEUTRAL = ROOT / "data" / "samples" / "versus_djin_vs_kaz_l3_neutral.zip"
OPTIONS = normalize_table(load_fallback()["kazuya"])
L3 = Difficulty.preset(3)


def validator(name, sub=None):
    data = json.loads((CONTRACTS / f"{name}.schema.json").read_text())
    if sub:
        data = {**data["$defs"][sub], "$defs": data["$defs"]}
    return Draft202012Validator(data, format_checker=FormatChecker())


SUMMARY_V = validator("round_summary")
ROUND_V = validator("metrics", "round")
PROFILE_V = validator("profile")
PLAN_V = validator("gameplan")


def contracts_validate():
    spec = importlib.util.spec_from_file_location("kumite_validate", CONTRACTS / "validate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def state_at(frame, round_=1, situation="neutral", adv=None, human=None, bot=None):
    state = build_state([idle(0, frame, **(human or {})), idle(1, frame, **(bot or {}))], 0, frame, SID)
    state["round"] = round_
    state["derived"]["situation"] = situation
    state["derived"]["frame_advantage"] = adv
    return state


def decision(frame, situation, action, correct, round_=1, **detail):
    info = {"start_frame": frame - 20, "correct": correct, "state_text": "The opponent is standing at close range."}
    info.update(detail)
    return {"t": "event", "session_id": SID, "frame": frame, "round": round_, "kind": "decision_point", "actor": 0, "target": 1,
            "situation": situation, "action": action, "detail": info}


def hit(frame, damage, round_=1):
    return {"t": "event", "session_id": SID, "frame": frame, "round": round_, "kind": "hit", "actor": 1, "target": 0,
            "move_id": 0x6DB, "hit_level": "low", "damage": damage, "frame_advantage": 3}


def round_end(frame, winner, round_=1):
    return {"t": "event", "session_id": SID, "frame": frame, "round": round_, "kind": "round_end", "detail": {"reason": "ko", "winner": winner}}


class LearningRig:
    def __init__(self, predictor=False, difficulty=L3, seed=0):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.learning = Learning("tester", "devil_jin", OPTIONS, difficulty, random.Random(seed), self.root, predictor=predictor)
        self.frame = 100
        self.round = 1
        self.records = []

    def feed(self, situation, action, correct, **detail):
        self.frame += 30
        state = state_at(self.frame, self.round)
        self.records += self.learning.step(state, [decision(self.frame, situation, action, correct, self.round, **detail)])
        return state

    def end_round(self, winner=1):
        self.frame += 10
        state = state_at(self.frame, self.round)
        out = self.learning.round_end(state, round_end(self.frame, winner, self.round))
        self.records += out
        self.round += 1
        self.frame = 0
        return out

    def close(self):
        self.tmp.cleanup()


class HabitTest(unittest.TestCase):
    def test_planted_habit_detected_in_under_8_samples(self):
        h = Habits()
        plan = ["hit", "hit", "blocked", "hit", "hit", "hit", "blocked"]
        detected = None
        for i, action in enumerate(plan, 1):
            h.observe("low_defense", action, action == "blocked")
            if h.active("low_defense") and detected is None:
                detected = i
        self.assertIsNotNone(detected)
        self.assertLess(detected, 8)
        self.assertEqual(h.active("low_defense")[0], "hit")
        self.assertGreaterEqual(h.active("low_defense")[1], 0.6)
        self.assertEqual(h.seen["low_defense"], 7)

    def test_habit_forgotten_after_it_stops(self):
        h = Habits()
        for _ in range(8):
            h.observe("low_defense", "hit", False)
        self.assertEqual(h.active("low_defense")[0], "hit")
        gone = None
        for i in range(1, 21):
            h.observe("low_defense", "blocked", True)
            active = h.active("low_defense")
            if gone is None and (active is None or active[0] != "hit"):
                gone = i
        self.assertIsNotNone(gone)
        self.assertLessEqual(gone, 20)
        self.assertEqual(h.active("low_defense")[0], "blocked")
        self.assertAlmostEqual(h.correct_rate("low_defense"), 1.0, delta=0.3)

    def test_not_active_below_four_samples(self):
        h = Habits()
        for _ in range(ACTIVE_N - 1):
            h.observe("throw_break", "none", False)
        self.assertIsNone(h.active("throw_break"))
        h.observe("throw_break", "none", False)
        self.assertEqual(h.active("throw_break")[0], "none")

    def test_new_session_halves_confidence(self):
        h = Habits({"low_defense": {"hit": [8.0, 1], "blocked": [0.0, 1]}})
        self.assertEqual(h.seen["low_defense"], 8)
        h.scale(0.5)
        self.assertEqual(h.seen["low_defense"], 4)
        self.assertAlmostEqual(h.n("low_defense"), 4.0)


class MasteryTest(unittest.TestCase):
    def test_fix_then_regress(self):
        m = Mastery()
        changes = [m.observe("low_defense", True) for _ in range(FIXED_N)]
        self.assertEqual(changes[-1], "fixed")
        self.assertTrue(m.fixed("low_defense"))
        self.assertGreaterEqual(m.p("low_defense"), 0.85)
        self.assertNotIn("fixed", changes[:-1])
        wrong = [m.observe("low_defense", False) for _ in range(5)]
        self.assertIn("regressed", wrong)
        self.assertFalse(m.fixed("low_defense"))

    def test_one_slip_does_not_erase_mastery(self):
        m = Mastery()
        for _ in range(FIXED_N):
            m.observe("low_defense", True)
        m.observe("low_defense", False)
        self.assertTrue(m.fixed("low_defense"))

    def test_forgetting_and_retest(self):
        m = Mastery({"throw_break": {"p_learned": 0.9, "observations": 10, "fixed": True, "last_retest": None}})
        m.forget()
        self.assertAlmostEqual(m.p("throw_break"), 0.9 * 0.98)
        self.assertTrue(m.retest_due("throw_break", 1))
        m.stamp_retest("throw_break", 1)
        self.assertFalse(m.retest_due("throw_break", 2))
        self.assertTrue(m.retest_due("throw_break", 3))
        self.assertIsInstance(m.skills["throw_break"]["last_retest"], str)


class BanditTest(unittest.TestCase):
    def pulls(self, b, rng, key, arms, rewards, n):
        picks = []
        for _ in range(n):
            arm = b.pull(key, arms, 0.5, rng)
            b.reward(key, arm, rewards[arm])
            picks.append(arm)
        return picks

    def test_prefers_rewarding_arm_then_switches(self):
        b = Bandit()
        rng = random.Random(1)
        arms = ["d+4", "db+3", "db+4"]
        picks = self.pulls(b, rng, "low_defense|hit", arms, {"d+4": 1.0, "db+3": 0.0, "db+4": 0.0}, 40)
        self.assertEqual(Counter(picks[-15:]).most_common(1)[0][0], "d+4")
        self.assertGreater(b.rate("low_defense|hit", "d+4"), b.rate("low_defense|hit", "db+3"))
        picks = self.pulls(b, rng, "low_defense|hit", arms, {"d+4": 0.0, "db+3": 1.0, "db+4": 0.0}, 60)
        self.assertEqual(Counter(picks[-15:]).most_common(1)[0][0], "db+3")
        self.assertGreater(b.switches, 0)
        for arms_ in b.rates().values():
            for rate in arms_.values():
                self.assertTrue(0 <= rate <= 1)

    def test_discount_bounds_counts(self):
        b = Bandit()
        rng = random.Random(0)
        for _ in range(200):
            arm = b.pull("k", ["a"], 1.0, rng)
            b.reward("k", arm, 1.0)
        s, f = b.arms["k"]["a"]
        self.assertLess(s, 11)


class PredictorTest(unittest.TestCase):
    @unittest.skipIf(forest is None, "river not installed")
    def test_accuracy_rises_and_pickles(self):
        p = Predictor(seed=0)
        rows = [({"situation": "low_defense", "distance": "close", "last1": "hit"}, "hit"),
                ({"situation": "throw_break", "distance": "close", "last1": "none"}, "break_2"),
                ({"situation": "sidestep_dir", "distance": "mid", "last1": "none"}, "none")]
        for i in range(60):
            p.observe(*rows[i % 3])
        self.assertIsNotNone(p.accuracy())
        self.assertGreater(p.accuracy(), 0.8)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.pkl"
            self.assertTrue(p.save(path))
            again = Predictor.load(path)
            guess = again.model.predict_proba_one(rows[0][0])
            self.assertEqual(max(guess, key=guess.get), "hit")
            missing = Predictor.load(Path(tmp) / "nope.pkl")
            self.assertTrue(missing.enabled)

    def test_disabled_predictor(self):
        p = Predictor(None)
        self.assertEqual(p.observe({"a": 1}, "x"), (None, False))
        self.assertIsNone(p.accuracy())


class KeysTest(unittest.TestCase):
    def test_after_block_pools_by_frame_class(self):
        self.assertEqual(learner_keys("after_block:df1", {"adv": -5}), ([PLUS_KEY, ANY_KEY], "after_block:df1"))
        self.assertEqual(learner_keys("after_block:b4", {"adv": 4}), ([MINUS_KEY, ANY_KEY], "after_block:b4"))
        self.assertEqual(learner_keys("after_block:0x69d", {"adv": 0}), ([PLUS_KEY, ANY_KEY], "after_block:0x69d"))
        self.assertEqual(learner_keys("low_defense", {}), (["low_defense"], None))

    def test_throw_filters(self):
        throws = {e["notation"]: e for e in OPTIONS["classes"]["throw"]}
        self.assertFalse(not_broken_by("1")(throws["1+3"]))
        self.assertTrue(not_broken_by("1")(throws["uf+1+2"]))
        self.assertTrue(not_broken_by("1+2")(throws["1+3"]))
        self.assertFalse(not_broken_by("1+2")(throws["uf+1+2"]))


class LearningTest(unittest.TestCase):
    def test_pooled_after_block_drives_boosts(self):
        rig = LearningRig()
        try:
            moves = ["df1", "b4", "f4", "d2", "df1"]
            for i, move in enumerate(moves):
                rig.feed(f"after_block:{move}", "press", False, adv=-4 - i % 2)
            L = rig.learning
            self.assertEqual(L.habits.seen[PLUS_KEY], 5)
            self.assertEqual(L.habits.seen[ANY_KEY], 5)
            self.assertEqual(L.habits.seen["after_block:df1"], 2)
            self.assertIn(PLUS_KEY, L.mastery.skills)
            self.assertNotIn("after_block:df1", L.mastery.skills)
            self.assertNotIn(MINUS_KEY, L.habits.counts)
            defense = state_at(500, situation="defense", adv=-5)
            boosts = L.boosts(defense)
            self.assertIn("mid", boosts)
            self.assertEqual(boosts["mid"]["situation"], PLUS_KEY)
            self.assertEqual(boosts["mid"]["action"], "press")
            self.assertGreater(boosts["mid"]["factor"], 1.0)
            self.assertNotIn("mid", L.boosts(state_at(500)))
            targets = L.targets()
            self.assertEqual([t["situation"] for t in targets], [PLUS_KEY, ANY_KEY])
            self.assertTrue(all(t["situation"] != "after_block:df1" for t in targets))
        finally:
            rig.close()

    def test_bot_minus_is_coach_detail_only(self):
        rig = LearningRig()
        try:
            for _ in range(5):
                rig.feed("after_block:f4", "press", False, adv=3)
            L = rig.learning
            self.assertEqual(L.habits.active(MINUS_KEY)[0], "press")
            boosts = L.boosts(state_at(500, situation="defense", adv=-5))
            self.assertEqual(boosts["mid"]["situation"], ANY_KEY)
            self.assertTrue(all(b["situation"] != MINUS_KEY for b in boosts.values()))
            self.assertEqual(L.boosts(state_at(500)), {})
            rows = L.habit_rows(L.pooled_keys())
            self.assertIn(MINUS_KEY, rows)
            self.assertNotIn("after_block:f4", rows)
            self.assertTrue(all(t["situation"] != MINUS_KEY for t in L.targets()))
        finally:
            rig.close()

    def test_low_habit_boosts_low_and_bandit_picks_true_lows(self):
        rig = LearningRig()
        try:
            for _ in range(6):
                rig.feed("low_defense", "hit", False)
            L = rig.learning
            boosts = L.boosts(state_at(400))
            self.assertEqual(set(boosts), {"low"})
            expected = 1 + 3.0 * L3.exploit_weight * 0.5
            self.assertAlmostEqual(boosts["low"]["factor"], expected, places=2)
            picks = Counter()
            for _ in range(30):
                entry = L.pick("low", OPTIONS["classes"]["low"], boosts["low"], L3)
                picks[entry["notation"]] += 1
                self.assertEqual(entry["hit_level"], "low")
            self.assertNotIn("d+2", picks)
            self.assertNotIn("d+1", picks)
            for _ in range(2):
                rig.feed("low_defense", "blocked", True)
            scaled = L.boosts(state_at(800))
            self.assertIn("low", scaled)
            self.assertGreater(scaled["low"]["factor"], boosts["low"]["factor"])
        finally:
            rig.close()

    def test_fixed_habit_stops_exploit_and_retests(self):
        rig = LearningRig()
        try:
            for _ in range(5):
                rig.feed("low_defense", "hit", False)
            for _ in range(FIXED_N + 2):
                rig.feed("low_defense", "blocked", True)
            L = rig.learning
            fixed = [r for r in rig.records if r.get("t") == "learning_event" and r["event"] == "fixed"]
            self.assertEqual([r["situation"] for r in fixed], ["low_defense"])
            self.assertTrue(L.mastery.fixed("low_defense"))
            probe = state_at(900)
            first = L.boosts(probe)
            self.assertIn("mid", first)
            self.assertTrue(first["mid"]["retest"])
            L.decided("mid", first, probe)
            self.assertEqual(L.boosts(probe), {})
            self.assertIsInstance(L.mastery.skills["low_defense"]["last_retest"], str)
            later = copy.deepcopy(probe)
            later["round"] = 3
            self.assertTrue(L.boosts(later)["mid"]["retest"])
            self.assertEqual(L.targets(), [])
            for _ in range(5):
                rig.feed("low_defense", "hit", False)
            regressed = [r for r in rig.records if r.get("t") == "learning_event" and r["event"] == "regressed"]
            self.assertEqual(len(regressed), 1)
        finally:
            rig.close()

    def test_bandit_reward_from_outcome(self):
        rig = LearningRig()
        try:
            for _ in range(5):
                rig.feed("low_defense", "hit", False)
            L = rig.learning
            probe = state_at(600)
            boosts = L.boosts(probe)
            entry = L.pick("low", OPTIONS["classes"]["low"], boosts["low"], L3)
            L.decided("low", boosts, probe)
            self.assertEqual(L.pull["frame"], 600)
            mine = int(entry["move_id"], 16)
            other = 0x643
            L.step(state_at(610), [dict(hit(610, 30), move_id=other)])
            self.assertIsNotNone(L.pull)
            L.step(state_at(620), [dict(hit(620, 20), move_id=mine)])
            self.assertIsNone(L.pull)
            s, f = L.bandit.arms["low_defense|hit"][entry["notation"]]
            self.assertAlmostEqual(s, 0.8)
            self.assertAlmostEqual(f, 0.2)
            entry = L.pick("low", OPTIONS["classes"]["low"], boosts["low"], L3)
            L.decided("low", boosts, state_at(700))
            L.step(state_at(705, bot={"move_id": int(entry["move_id"], 16), "free_movement": 0, "frame_in_move": 3, "move_total": 30}), [])
            self.assertTrue(L.pull["started"])
            L.step(state_at(800, human={"health": 160}), [])
            self.assertIsNone(L.pull)
            self.assertAlmostEqual(sum(v[0] for v in L.bandit.arms["low_defense|hit"].values()), 0.8 * 0.9, places=3)
            self.assertAlmostEqual(L.bandit.arms["low_defense|hit"][entry["notation"]][1] % 1.0 if entry["notation"] != "db+3" else 0.0, 0.0, places=3)
            before = {k: list(v) for k, v in L.bandit.arms["low_defense|hit"].items()}
            entry = L.pick("low", OPTIONS["classes"]["low"], boosts["low"], L3)
            L.decided("low", boosts, state_at(900))
            L.step(state_at(1000, human={"health": 100}), [])
            self.assertIsNone(L.pull)
            after = L.bandit.arms["low_defense|hit"]
            self.assertTrue(all(after[k][0] + after[k][1] <= before[k][0] + before[k][1] for k in before))
            entry = L.pick("low", OPTIONS["classes"]["low"], boosts["low"], L3)
            L.decided("wait", {}, state_at(1100))
            self.assertIsNone(L.pull)
            self.assertIsNone(L.next_pull)
        finally:
            rig.close()

    def test_overlapping_pick_settles_the_first(self):
        rig = LearningRig()
        try:
            for _ in range(5):
                rig.feed("low_defense", "hit", False)
            L = rig.learning
            boosts = L.boosts(state_at(600))
            first = L.pick("low", OPTIONS["classes"]["low"], boosts["low"], L3)
            L.decided("low", boosts, state_at(600))
            mine = int(first["move_id"], 16)
            L.step(state_at(605, bot={"move_id": mine, "free_movement": 0, "frame_in_move": 2, "move_total": 30}), [])
            L.pick("low", OPTIONS["classes"]["low"], boosts["low"], L3)
            L.decided("low", boosts, state_at(611))
            self.assertEqual(len(L.pulls), 2)
            L.step(state_at(612, human={"health": 170}), [dict(hit(612, 20), move_id=mine)])
            s, f = L.bandit.arms["low_defense|hit"][first["notation"]]
            self.assertAlmostEqual(s + f, 1.0, places=3)
            self.assertAlmostEqual(s, 0.8, places=3)
            self.assertEqual(len(L.pulls), 1)
            self.assertEqual(L.pull["frame"], 611)
            L.decided("wait", {}, state_at(620))
            self.assertEqual(len(L.pulls), 1)
        finally:
            rig.close()

    def test_round_change_settles_a_started_pull(self):
        rig = LearningRig()
        try:
            for _ in range(5):
                rig.feed("low_defense", "hit", False)
            L = rig.learning
            boosts = L.boosts(state_at(600))
            entry = L.pick("low", OPTIONS["classes"]["low"], boosts["low"], L3)
            L.decided("low", boosts, state_at(600))
            mine = int(entry["move_id"], 16)
            L.step(state_at(605, bot={"move_id": mine, "free_movement": 0, "frame_in_move": 2, "move_total": 30}), [])
            L.step(state_at(615, human={"health": 165}), [])
            out = L.step(state_at(0, round_=2), [round_end(615, 1, 1)])
            self.assertEqual([r["t"] for r in out], ["round_summary"])
            self.assertEqual(out[0]["round"], 1)
            self.assertEqual(out[0]["frame"], 615)
            self.assertEqual(out[0]["human_damage_taken"], 25)
            self.assertEqual(out[0]["exploited"], ["low_defense"])
            s, f = L.bandit.arms["low_defense|hit"][entry["notation"]]
            self.assertAlmostEqual((s, f), (0.0, 1.0), places=3)
            self.assertEqual(L.pulls, [])
            self.assertEqual(L.rounds[-1]["round"], 1)
            self.assertEqual(L.round, 2)
            self.assertEqual(L.damage, [0, 0])
        finally:
            rig.close()

    def test_timeout_round_end_keeps_its_round(self):
        rig = LearningRig()
        try:
            for _ in range(4):
                rig.feed("low_defense", "hit", False)
            L = rig.learning
            L.step(state_at(rig.frame + 5, human={"health": 150}), [hit(rig.frame + 5, 40)])
            out = L.step(state_at(0, round_=2), [round_end(4000, None, 1), {"t": "event", "session_id": SID, "frame": 0, "round": 2, "kind": "round_start", "detail": {"reason": "counter_reset"}}])
            self.assertEqual(len(out), 1)
            summary = out[0]
            self.assertEqual((summary["round"], summary["frame"], summary["winner"]), (1, 4000, None))
            self.assertEqual(summary["human_damage_taken"], 40)
            self.assertEqual(summary["biggest_moments"][0]["damage"], 40)
            self.assertEqual([r["round"] for r in L.rounds], [1])
            self.assertEqual(L.rounds[0]["habits"]["low_defense"]["n"], 4)
            self.assertEqual(L.round, 2)
            out = L.step(state_at(100, round_=2), [round_end(100, 0, 2)])
            self.assertEqual([r["round"] for r in L.rounds], [1, 2])
        finally:
            rig.close()

    def test_moments_follow_the_decision_that_caused_them(self):
        rig = LearningRig()
        try:
            L = rig.learning
            L.step(state_at(100), [decision(100, "sidestep_dir", "none", False, start_frame=90)])
            low = dict(hit(120, 18), move_id=0x6DB)
            out = L.step(state_at(122), [low, decision(122, "low_defense", "hit", False, start_frame=120)])
            self.assertEqual(L.moments[-1]["situation"], "low_defense")
            L.step(state_at(200), [decision(200, "sidestep_dir", "none", False, start_frame=190)])
            throw = {"t": "event", "session_id": SID, "frame": 230, "round": 1, "kind": "throw", "actor": 1, "target": 0, "move_id": 0x7DF}
            L.step(state_at(230), [throw])
            L.step(state_at(260, human={"health": 155}), [])
            L.step(state_at(262, human={"health": 155}), [decision(262, "throw_break", "none", False, start_frame=230)])
            throws = [m for m in L.moments if m["kind"] == "throw"]
            self.assertEqual(throws[0]["damage"], 35)
            self.assertEqual(throws[0]["situation"], "throw_break")
            summary = L.summary(state_at(300), 1)
            self.assertEqual([m["kind"] for m in summary["biggest_moments"]], ["hit", "throw"])
            self.assertTrue(all("_exact" not in m for m in summary["biggest_moments"]))
            L.step(state_at(400), [{"t": "event", "session_id": SID, "frame": 400, "round": 1, "kind": "throw", "actor": 1, "target": 0, "move_id": 0x7DF}])
            L.step(state_at(410), [{"t": "event", "session_id": SID, "frame": 410, "round": 1, "kind": "throw_break", "actor": 0, "target": 1}])
            self.assertEqual(len([m for m in L.moments if m["kind"] == "throw"]), 1)
            L.step(state_at(472), [decision(472, "after_block:df1", "press", False, start_frame=460, adv=-5)])
            L.step(state_at(500), [dict(hit(500, 12), move_id=0x6A6)])
            self.assertEqual(L.moments[-1]["situation"], "after_block:df1")
        finally:
            rig.close()

    def test_crouch_counters_never_pick_highs(self):
        from game.options import load_options
        table = load_options("kazuya")[0]
        rig = LearningRig()
        try:
            L = rig.learning
            for _ in range(5):
                rig.feed("after_block:df1", "duck", False, adv=-3)
                rig.feed("low_defense", "blocked", True)
            boosts = L.boosts(state_at(900, situation="defense", adv=-3))
            self.assertEqual(set(boosts), {"mid", "throw", "launcher"})
            for cls in ("mid", "launcher"):
                for _ in range(40):
                    entry = L.pick(cls, table["classes"][cls], boosts[cls], L3)
                    self.assertIsNotNone(entry)
                    self.assertNotEqual(entry["hit_level"], "high", entry["notation"])
        finally:
            rig.close()

    def test_fixed_bot_plus_suppresses_any_fallback(self):
        rig = LearningRig()
        try:
            L = rig.learning
            for _ in range(FIXED_N):
                rig.feed("after_block:df1", "press", False, adv=-4)
            for _ in range(3):
                rig.feed("after_block:b4", "block_high", True, adv=-4)
            self.assertTrue(L.mastery.fixed(PLUS_KEY))
            for _ in range(8):
                rig.feed("after_block:f4", "press", False, adv=3)
            self.assertEqual(L.habits.active(ANY_KEY)[0], "press")
            probe = state_at(900, situation="defense", adv=-5)
            boosts = L.boosts(probe)
            self.assertTrue(boosts["mid"]["retest"])
            L.decided("mid", boosts, probe)
            self.assertEqual(L.boosts(probe), {})
            self.assertFalse(L.mastery.retest_due(PLUS_KEY, 1))
        finally:
            rig.close()

    def test_predictor_sees_the_decision_start_state(self):
        rig = LearningRig()
        try:
            L = rig.learning
            seen = []
            L.predictor.observe = lambda feats, label: seen.append(feats) or (None, False)
            L.step(state_at(100, bot={"position": (-6000.0, 1040.0, 300.0)}), [])
            L.step(state_at(130, bot={"position": (-6000.0, 1040.0, 2000.0)}), [decision(130, "low_defense", "hit", False, start_frame=100)])
            self.assertEqual(seen[-1]["distance"], "close")
            L.step(state_at(200, bot={"position": (-6000.0, 1040.0, 2000.0)}), [decision(200, "low_defense", "hit", False, start_frame=5)])
            self.assertEqual(seen[-1]["distance"], "far")
        finally:
            rig.close()

    def test_pull_matches_every_table_id(self):
        from game.options import load_options
        table = load_options("kazuya")[0]
        jab = next(e for e in table["classes"]["mid"] if e["notation"] == "1")
        self.assertEqual(sorted(jab["move_ids"]), ["0x659", "0x65a"])
        rig = LearningRig()
        try:
            for _ in range(5):
                rig.feed("after_block:df1", "press", False, adv=-4)
            L = rig.learning
            probe = state_at(600, situation="defense", adv=-4)
            boosts = L.boosts(probe)
            entry = L.pick("mid", [jab], boosts["mid"], L3)
            self.assertEqual(entry["notation"], "1")
            L.decided("mid", boosts, probe)
            self.assertEqual(L.pull["ids"], {0x659, 0x65A})
            L.step(state_at(603, bot={"move_id": 0x659, "free_movement": 0, "frame_in_move": 1, "move_total": 27}), [])
            self.assertTrue(L.pull["started"])
            L.step(state_at(612), [dict(hit(612, 7), move_id=0x659)])
            self.assertEqual(L.pulls, [])
            s, f = L.bandit.arms[f"{PLUS_KEY}|press"]["1"]
            self.assertAlmostEqual(s, 7 / 25, places=3)
        finally:
            rig.close()

    def test_movement_pull_settles_by_health_delta(self):
        rig = LearningRig()
        try:
            for _ in range(5):
                rig.feed("after_block:b4", "backdash", True, adv=-4)
            L = rig.learning
            probe = state_at(600, situation="defense", adv=-4)
            boosts = L.boosts(probe)
            self.assertIn("approach", boosts)
            entry = L.pick("approach", OPTIONS["classes"]["approach"], boosts["approach"], L3)
            L.decided("approach", boosts, probe)
            self.assertTrue(L.pull["started"])
            self.assertEqual(L.pull["ids"], set())
            L.step(state_at(620), [hit(620, 20)])
            self.assertEqual(len(L.pulls), 1)
            L.step(state_at(700, human={"health": 160}), [])
            self.assertEqual(L.pulls, [])
            s, f = L.bandit.arms[f"{PLUS_KEY}|backdash"][entry["notation"]]
            self.assertAlmostEqual(s, 1.0, places=3)
        finally:
            rig.close()

    def test_throw_moment_tracks_the_throw_itself(self):
        rig = LearningRig()
        try:
            L = rig.learning
            thrown = {"being_thrown": 0xE000001F}
            L.step(state_at(230), [{"t": "event", "session_id": SID, "frame": 230, "round": 1, "kind": "throw", "actor": 1, "target": 0, "move_id": 0x7DF}])
            for f in range(231, 330):
                health = 190 if f < 260 else 171 if f < 329 else 155
                L.step(state_at(f, human=dict(thrown, health=health)), [])
            for f in range(330, 340):
                L.step(state_at(f, human={"health": 155}), [])
            self.assertEqual(L.throw_moments, [])
            throw = [m for m in L.moments if m["kind"] == "throw"][0]
            self.assertEqual(throw["damage"], 35)
            L.step(state_at(360, human={"health": 140}), [dict(hit(360, 15), move_id=0x6DB)])
            self.assertEqual(throw["damage"], 35)
            L.step(state_at(400, human={"health": 140}), [{"t": "event", "session_id": SID, "frame": 400, "round": 1, "kind": "throw", "actor": 1, "target": 0, "move_id": 0x7DF}])
            L.step(state_at(410, human=dict(thrown, health=130)), [])
            L.step(state_at(420, human=dict(thrown, health=130)), [dict(hit(420, 12), move_id=0x6A6)])
            second = [m for m in L.moments if m["kind"] == "throw"][1]
            self.assertEqual(second["damage"], 10)
            self.assertEqual(L.throw_moments, [])
            L.step(state_at(500, human={"health": 118}), [{"t": "event", "session_id": SID, "frame": 500, "round": 1, "kind": "throw", "actor": 1, "target": 0, "move_id": 0x7DF}])
            L.step(state_at(540, human={"health": 118}), [])
            self.assertEqual(L.throw_moments, [])
            summary = L.summary(state_at(600), 1)
            self.assertEqual([m["damage"] for m in summary["biggest_moments"]], [35, 15, 12])
            L.step(state_at(610), [decision(610, "low_defense", "hit", False, start_frame=None)])
        finally:
            rig.close()

    def test_unfinished_pull(self):
        rig = LearningRig()
        try:
            for _ in range(5):
                rig.feed("low_defense", "hit", False)
            L = rig.learning
            boosts = L.boosts(state_at(600))
            entry = L.pick("low", OPTIONS["classes"]["low"], boosts["low"], L3)
            L.decided("low", boosts, state_at(600))
            L.step(state_at(700, human={"health": 120}), [])
            self.assertIsNone(L.pull)
            s, f = L.bandit.arms["low_defense|hit"][entry["notation"]]
            self.assertEqual((s, f), (0.0, 0.0))
        finally:
            rig.close()

    def test_round_end_records_validate_and_persist(self):
        rig = LearningRig(predictor=forest is not None)
        try:
            for _ in range(6):
                rig.feed("low_defense", "hit", False)
            rig.learning.step(state_at(rig.frame + 5, human={"health": 150}), [hit(rig.frame + 5, 40)])
            out = rig.end_round(winner=1)
            self.assertEqual([r["t"] for r in out], ["round_summary"])
            summary = out[0]
            self.assertEqual(list(SUMMARY_V.iter_errors(summary)), [])
            self.assertEqual(summary["winner"], 1)
            self.assertEqual(summary["human_damage_taken"], 40)
            self.assertEqual(summary["bot_damage_taken"], 0)
            self.assertEqual(summary["top_habits"][0]["situation"], "low_defense")
            self.assertEqual(summary["biggest_moments"][0]["damage"], 40)
            self.assertEqual(summary["biggest_moments"][0]["situation"], "low_defense")
            L = rig.learning
            self.assertEqual(len(L.rounds), 1)
            self.assertEqual(list(ROUND_V.iter_errors(L.rounds[0])), [])
            self.assertEqual(L.rounds[0]["habits"]["low_defense"]["action"], "hit")
            self.assertEqual(list(PROFILE_V.iter_errors(L.profile())), [])
            self.assertTrue(L.profile_path.exists())
            self.assertTrue(L.learning_path.exists())
            self.assertEqual(L.detected_round, {"low_defense": 1})
            module = contracts_validate()
            self.assertEqual(module.check_jsonl(module.load_schemas(), L.learning_path), 0)
            again = Learning("tester", "devil_jin", OPTIONS, L3, random.Random(0), rig.root, predictor=forest is not None)
            self.assertEqual(again.sessions, 2)
            self.assertEqual(again.habits.seen["low_defense"], 3)
            self.assertLess(again.mastery.p("low_defense"), L.mastery.p("low_defense"))
            self.assertEqual(again.predictor.enabled, forest is not None)
            if forest is not None:
                self.assertTrue(L.predictor_path.exists())
                self.assertEqual(L.profile()["predictor"], f"profiles/tester_devil_jin.predictor.pkl")
            metrics = L.metrics()
            self.assertEqual(list(validator("metrics").iter_errors(metrics)), [])
        finally:
            rig.close()


class TacticalIntegrationTest(unittest.TestCase):
    def test_habit_source_and_plan_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            learning = Learning("tester", "devil_jin", OPTIONS, L3, random.Random(0), tmp, predictor=False)
            rig = TRig(difficulty=L3)
            rig.tactical.learning = learning
            rig.run(frames("close", n=12))
            plans = [r for r in rig.records if r.get("t") == "plan"]
            self.assertEqual(len(plans), 1)
            self.assertEqual(plans[0]["target_habits"], [])
            for i in range(6):
                learning.step(state_at(12 + i, situation="neutral"), [decision(12 + i, "low_defense", "hit", False)])
            rig.run(frames("close", start=20, n=120))
            plans = [r for r in rig.records if r.get("t") == "plan"]
            self.assertEqual(len(plans), 2)
            self.assertEqual(plans[1]["target_habits"][0]["situation"], "low_defense")
            self.assertIn("low", plans[1]["note"])
            body = {k: v for k, v in plans[1].items() if k not in ("t", "round", "frame", "session_id")}
            self.assertEqual(list(PLAN_V.iter_errors(body)), [])
            decisions = rig.decisions()
            habit = [r for r in decisions if r["source"] == "habit"]
            self.assertTrue(habit)
            self.assertTrue(all(r["chosen"] == "low" for r in habit))
            self.assertTrue(all(r["tactical"]["hit_level"] == "low" for r in habit))
            self.assertTrue(all("low_defense" in r["tactical"]["boosts"]["low"]["situation"] for r in habit))
            lows = [r for r in decisions if r["frame"] >= 20 and r["chosen"] == "low"]
            self.assertTrue(all(r["source"] == "habit" for r in lows))


class NeutralSampleTest(unittest.TestCase):
    def test_low_defense_detected_and_low_boosted(self):
        records = load_jsonl(NEUTRAL)
        states = [r for r in records if r["t"] == "state"]
        meta = json.loads(find_session(NEUTRAL, states[0]["session_id"])[1])
        with tempfile.TemporaryDirectory() as tmp:
            run = run_learning(states, "tester", 3, meta["mode"], root=tmp, seed=0, tactical=True, predictor=forest is not None)
            L = run.learning
            table = Counter((e["situation"], e["action"]) for e in run.decisions)
            self.assertEqual(table[("low_defense", "hit")], 13)
            self.assertEqual(L.habits.active("low_defense")[0], "hit")
            self.assertGreaterEqual(L.habits.active("low_defense")[1], 0.6)
            self.assertLessEqual(L.detected_round["low_defense"], 2)
            final = run.boosts[-1][1]
            self.assertIn("low", final)
            self.assertGreater(final["low"]["factor"], 1.0)
            self.assertEqual((final["low"]["situation"], final["low"]["action"]), ("low_defense", "hit"))
            self.assertTrue(all(key.startswith(("low_defense", "throw_break", "sidestep_dir", "after_block:bot_", "after_block:any"))
                                for rec in L.rounds for key in rec["habits"]))
            self.assertIn(ANY_KEY, L.rounds[-1]["habits"])
            self.assertTrue(any(k.startswith("after_block:") and k not in (PLUS_KEY, MINUS_KEY, ANY_KEY) for k in L.habits.counts))
            picks = [r for r in run.records if r.get("t") == "tactical" and r.get("source") == "habit"]
            self.assertGreater(len(picks), 10)
            low_picks = [r for r in picks if r["chosen"] == "low"]
            self.assertGreater(len(low_picks), len(picks) // 2)
            self.assertTrue(all(r["tactical"]["hit_level"] == "low" for r in low_picks))
            self.assertEqual(len(run.summaries), len(meta["rounds"]))
            for s in run.summaries:
                self.assertEqual(list(SUMMARY_V.iter_errors(s)), [])
            for rec in L.rounds:
                self.assertEqual(list(ROUND_V.iter_errors(rec)), [])
            self.assertEqual(list(PROFILE_V.iter_errors(L.profile())), [])
            self.assertTrue(any(s["exploited"] == ["low_defense"] or "low_defense" in s["exploited"] for s in run.summaries))
            plans = [r for r in run.records if r.get("t") == "plan"]
            self.assertTrue(any(t["situation"] == "low_defense" for p in plans for t in p["target_habits"]))
            if forest is not None:
                self.assertTrue(any(rec["prediction_accuracy"] is not None for rec in L.rounds))


if __name__ == "__main__":
    unittest.main()
