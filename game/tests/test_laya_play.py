import json
import random
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from game import laya as L
from game.difficulty import Difficulty
from game.finetune import OPTIONS, QUESTIONS, action_distribution, laya_prior
from game.hotloop import fmt_record
from game.learning import ACTIVE_N, ACTIVE_P, Learning
from game.replay_learn import run_learning
from game.summarize import load_jsonl
from game.tactical import LAYA_WEIGHT, Tactical
from game.tests.test_tactical import LATENCY, OPTIONS as KAZ_OPTIONS, TRig, frames

ROOT = Path(__file__).resolve().parents[2]
NEUTRAL = ROOT / "data" / "samples" / "versus_djin_vs_kaz_l3_neutral.zip"


def answers(presses=0.5, ducks=0.5, steps=0.5, passive=0.5):
    return {"opp_presses": {"p": presses, "confidence": 0.0}, "opp_ducks": {"p": ducks, "confidence": 0.0},
            "opp_steps": {"p": steps, "confidence": 0.0}, "opp_passive": {"p": passive, "confidence": 0.0}}


class FakeOracle:
    def __init__(self, reply=None, version=3):
        self.reply = reply
        self.version = version
        self.asked = []

    def submit(self, text):
        self.asked.append(text)

    def answer(self, text):
        return self.reply(text) if callable(self.reply) else self.reply


class FakeLaya:
    def __init__(self, name="a", fail=False, delay=0.0):
        self.name = name
        self.fail = fail
        self.delay = delay
        self.calls = []
        self.released = False
        self.parked = False
        self.warmed = False

    def predict(self, text, questions=None):
        self.calls.append(text)
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("cuda gone")
        return answers(presses=0.9 if "close" in text else 0.1)

    def warmup(self):
        self.warmed = True

    def park(self):
        self.parked = True
        return True

    def unpark(self):
        self.parked = False
        return True

    def release(self):
        self.released = True


def wait_for(check, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.005)
    return check()


def learning(root, seed=0):
    return Learning("tester", "devil_jin", KAZ_OPTIONS, Difficulty.preset(3), random.Random(seed), root, predictor=False, fresh=True)


def plant(learn, situation, actions):
    for action in actions:
        learn.habits.observe(situation, action, action in ("blocked", "low_parry"))


class PriorTest(unittest.TestCase):
    def test_answers_become_a_distribution_over_each_situations_actions(self):
        prior = laya_prior(answers(presses=0.9, ducks=0.1, steps=0.1, passive=0.1))
        self.assertEqual(set(prior), {"after_block", "low_defense", "sidestep_dir"})
        for fam, dist in prior.items():
            self.assertEqual(set(dist), set(OPTIONS[fam]))
            self.assertAlmostEqual(sum(dist.values()), 1.0, places=9)
        self.assertEqual(max(prior["after_block"], key=prior["after_block"].get), "press")
        self.assertAlmostEqual(prior["after_block"]["press"], prior["after_block"]["throw"])
        self.assertAlmostEqual(prior["low_defense"]["blocked"], 0.1)
        self.assertAlmostEqual(prior["low_defense"]["hit"], 0.3)
        self.assertAlmostEqual(prior["sidestep_dir"]["none"], 0.9)
        self.assertIsNone(action_distribution("throw_break", answers()))
        self.assertEqual(laya_prior({}), {})


class EstimateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.learn = learning(Path(self.tmp.name))

    def test_weight_zero_is_the_habit_estimate(self):
        plant(self.learn, "low_defense", ["hit"] * 6)
        prior = {"low_defense": {"blocked": 1.0, "hit": 0.0, "jumped": 0.0, "low_parry": 0.0}}
        self.assertEqual(self.learn.estimate("low_defense", prior, 0.0), self.learn.habits.active("low_defense"))
        self.assertEqual(self.learn.estimate("low_defense"), self.learn.habits.active("low_defense"))

    def test_blend_makes_a_close_habit_active_toward_layas_action(self):
        plant(self.learn, "low_defense", ["hit", "blocked"] * 3)
        self.assertIsNone(self.learn.habits.active("low_defense"))
        prior = {"low_defense": {"blocked": 0.9, "hit": 0.1 / 3, "jumped": 0.1 / 3, "low_parry": 0.1 / 3}}
        action, p = self.learn.estimate("low_defense", prior, LAYA_WEIGHT)
        expected = (1 - LAYA_WEIGHT) * self.learn.habits.p("low_defense", "blocked") + LAYA_WEIGHT * 0.9
        self.assertEqual(action, "blocked")
        self.assertAlmostEqual(p, expected)
        self.assertGreaterEqual(p, ACTIVE_P)
        boosts = self.learn.boosts({"round": 1, "derived": {"situation": "neutral", "frame_advantage": None}}, None, prior, LAYA_WEIGHT)
        self.assertEqual({c: b["action"] for c, b in boosts.items()}, {"mid": "blocked", "throw": "blocked"})
        self.assertEqual(boosts["mid"]["laya_p"], 0.9)

    def test_laya_alone_never_activates_a_habit_without_enough_samples(self):
        plant(self.learn, "low_defense", ["blocked"] * (ACTIVE_N - 1))
        prior = {"low_defense": {"blocked": 1.0, "hit": 0.0, "jumped": 0.0, "low_parry": 0.0}}
        self.assertIsNone(self.learn.estimate("low_defense", prior, 1.0))


def laya_rig(root, oracle, weight=LAYA_WEIGHT):
    rig = TRig()
    learn = learning(root)
    rig.learning = learn
    rig.tactical = Tactical(rig.seq, rig.difficulty, LATENCY, KAZ_OPTIONS, rig.rng, learning=learn, laya=oracle, laya_weight=weight,
                            recent=lambda: [])
    return rig


class TacticalLayaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_ready_answer_is_recorded_as_laya_with_prediction_and_probabilities(self):
        oracle = FakeOracle(answers(presses=0.2, ducks=0.95, steps=0.1, passive=0.7), version=4)
        rig = laya_rig(self.root, oracle)
        plant(rig.learning, "low_defense", ["hit", "blocked"] * 3)
        rig.run(frames("close", n=30))
        recs = rig.decisions()
        self.assertTrue(recs)
        self.assertTrue(oracle.asked)
        self.assertTrue(all(t.startswith("The opponent is standing") for t in oracle.asked))
        for rec in recs:
            ask = rec["tactical"]["laya"]
            self.assertEqual(rec["source"], "laya")
            self.assertEqual(rec["frame_asked"], rec["frame"])
            self.assertEqual((ask["ready"], ask["version"], ask["weight"]), (True, 4, LAYA_WEIGHT))
            self.assertEqual(set(ask["p"]), set(QUESTIONS))
            self.assertEqual(ask["prediction"]["low_defense"]["action"], "blocked")
            self.assertTrue(ask["changed"])
            self.assertEqual(rec["tactical"]["boosts"]["mid"]["action"], "blocked")
        line = fmt_record(recs[0])
        self.assertIn("laya ", line)
        self.assertIn("| laya v4 after_block=", line)
        self.assertIn("low_defense=blocked:", line)
        self.assertEqual(rig.tactical.laya_stats["answered"], len(recs))

    def test_not_ready_falls_back_to_the_habit_choice(self):
        rig = laya_rig(self.root, FakeOracle(None))
        plant(rig.learning, "low_defense", ["hit"] * 6)
        rig.run(frames("close", n=30))
        recs = rig.decisions()
        self.assertTrue(recs)
        for rec in recs:
            self.assertEqual(rec["tactical"]["laya"], {"ready": False})
            self.assertEqual(rec["frame_asked"], rec["frame"])
            self.assertEqual(rec["source"], "habit" if rec["chosen"] in rec["tactical"].get("boosts", {}) else "default")
        self.assertIn("habit", {r["source"] for r in recs})
        self.assertEqual(rig.tactical.laya_stats, {"decisions": len(recs), "answered": 0, "changed": 0})

    def test_an_answer_one_frame_old_counts_and_older_ones_do_not(self):
        reply = answers(ducks=0.9)
        tactical = laya_rig(self.root, FakeOracle(lambda text: reply if text == "prev" else None)).tactical
        tactical.texts = [(1, 10, "now"), (1, 9, "prev")]
        self.assertEqual(tactical.laya_answer(), (9, reply))
        rig = laya_rig(self.root, FakeOracle(None))
        rig.run(frames("close", n=3))
        self.assertEqual([t[1] for t in rig.tactical.texts], [2, 1])
        rig.run(frames("close", start=10, n=1))
        self.assertEqual([t[1] for t in rig.tactical.texts], [10])

    def test_laya_off_never_builds_state_text(self):
        rig = TRig().run(frames("close", n=20))
        self.assertEqual(rig.tactical.texts, [])
        self.assertTrue(all("laya" not in r["tactical"] for r in rig.decisions()))


def strip_laya(rec):
    rec = json.loads(json.dumps(rec))
    if rec.get("t") == "tactical" and "tactical" in rec:
        rec["tactical"].pop("laya", None)
    return rec


class ReplayBothPathsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not NEUTRAL.exists():
            raise unittest.SkipTest("neutral sample missing")
        cls.states = [r for r in load_jsonl(NEUTRAL) if r.get("t") == "state" and r["round"] <= 2]

    def replay(self, laya=None, weight=LAYA_WEIGHT):
        with tempfile.TemporaryDirectory() as tmp:
            run = run_learning(self.states, "replay", 3, "versus", root=tmp, seed=0, tactical=True, predictor=False, laya=laya,
                               laya_weight=weight)
        return run.records

    def test_laya_off_and_laya_never_ready_play_the_same_session(self):
        off = self.replay()
        never = self.replay(FakeOracle(None))
        picks = [r for r in off if r.get("t") == "tactical" and r["source"] != "reflex"]
        self.assertGreater(len(picks), 50)
        self.assertIn("habit", {r["source"] for r in picks})
        self.assertEqual([strip_laya(r) for r in never], off)
        self.assertTrue(all(r["tactical"]["laya"] == {"ready": False} for r in never if r.get("t") == "tactical" and r["source"] != "reflex"))

    def test_laya_at_weight_zero_only_relabels_the_source(self):
        def key(records):
            return [(r["round"], r["frame"], r["chosen"], r["tactical"]["move"], r["probabilities"]) for r in records
                    if r.get("t") == "tactical" and r["source"] != "reflex"]

        off = self.replay()
        zero = self.replay(FakeOracle(answers(presses=0.9, ducks=0.9, steps=0.1, passive=0.1)), weight=0.0)
        self.assertEqual(key(zero), key(off))
        self.assertEqual({r["source"] for r in zero if r.get("t") == "tactical" and r["source"] != "reflex"}, {"laya"})

    def test_a_confident_laya_changes_some_habit_targets(self):
        run = self.replay(FakeOracle(answers(presses=0.05, ducks=0.95, steps=0.05, passive=0.9)), weight=0.6)
        picks = [r for r in run if r.get("t") == "tactical" and r["source"] == "laya"]
        self.assertTrue(picks)
        self.assertTrue(any(r["tactical"]["laya"]["changed"] for r in picks))


class OracleTest(unittest.TestCase):
    def test_background_answers_are_cached_per_text(self):
        model = FakeLaya()
        oracle = L.Oracle(model, 2, log=lambda *a, **k: None).start()
        self.addCleanup(oracle.close)
        self.assertIsNone(oracle.answer("at close range"))
        oracle.submit("at close range")
        self.assertTrue(wait_for(lambda: oracle.answer("at close range") is not None))
        self.assertEqual(oracle.answer("at close range")["opp_presses"]["p"], 0.9)
        oracle.submit("at close range")
        time.sleep(0.05)
        self.assertEqual(model.calls, ["at close range"])
        self.assertTrue(oracle.thread.daemon)

    def test_latest_text_wins_while_busy(self):
        model = FakeLaya(delay=0.05)
        oracle = L.Oracle(model, 1, log=lambda *a, **k: None).start()
        self.addCleanup(oracle.close)
        for text in ("one", "two", "three", "four"):
            oracle.submit(text)
        self.assertTrue(wait_for(lambda: oracle.answer("four") is not None))
        self.assertLess(len(model.calls), 4)

    def test_attach_swaps_weights_clears_the_cache_and_releases_the_old_model(self):
        old, new = FakeLaya("old"), FakeLaya("new")
        oracle = L.Oracle(old, 1, threaded=False)
        oracle.submit("close")
        self.assertIsNotNone(oracle.answer("close"))
        oracle.attach(new, 2)
        self.assertTrue(old.released)
        self.assertEqual(oracle.version, 2)
        self.assertIsNone(oracle.answer("close"))
        oracle.submit("close")
        self.assertEqual(new.calls, ["close"])

    def test_parked_oracle_answers_nothing(self):
        model = FakeLaya()
        oracle = L.Oracle(model, 1, threaded=False)
        self.assertTrue(oracle.park())
        self.assertTrue(model.parked)
        oracle.submit("close")
        self.assertEqual(model.calls, [])
        oracle.unpark()
        self.assertFalse(model.parked)
        oracle.submit("close")
        self.assertEqual(model.calls, ["close"])

    def test_failed_predict_is_logged_once(self):
        logs = []
        oracle = L.Oracle(FakeLaya(fail=True), 1, log=lambda m, **_: logs.append(m), threaded=False)
        oracle.submit("a")
        oracle.submit("b")
        self.assertIsNone(oracle.answer("a"))
        self.assertEqual(len(logs), 1)
        self.assertIn("fall back to habits", logs[0])

    def test_without_weights_nothing_is_asked(self):
        oracle = L.Oracle(log=lambda *a, **k: None, threaded=False)
        oracle.submit("close")
        self.assertFalse(oracle.ready)
        self.assertIsNone(oracle.answer("close"))

    def test_startup_hands_the_loaded_model_and_version_to_the_oracle(self):
        with tempfile.TemporaryDirectory() as tmp:
            ft = Path(tmp) / "models" / "laya-ft"
            ft.mkdir(parents=True)
            for name in ("model.safetensors", "rl_agent_config.json"):
                (ft / name).write_text("x", encoding="utf-8")
            (ft / "meta.json").write_text(json.dumps({"version": 7}), encoding="utf-8")
            oracle = L.Oracle(threaded=False)
            with mock.patch.dict("os.environ", {"DATA_DIR": tmp}):
                got = L.startup(log=lambda *a, **k: None, rounds=1, factory=lambda model: L.Laya(model, agent=L.FakeAgent(0.7)),
                                on_ready=oracle.attach)
            self.assertIs(oracle.laya, got)
            self.assertEqual(oracle.version, 7)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class ReloaderTest(unittest.TestCase):
    def make(self, versions, factory=None):
        self.logs = []
        self.clock = Clock()
        self.old = FakeLaya("old")
        self.oracle = L.Oracle(self.old, 1, threaded=False)
        self.loaded = []

        def build(model):
            got = FakeLaya("new")
            self.loaded.append(got)
            return got

        self.versions = iter(versions)
        return L.Reloader(self.oracle, log=lambda m, **_: self.logs.append(m), factory=factory or build,
                          version_of=lambda: next(self.versions), clock=self.clock, park_max=60.0)

    def test_new_version_loads_in_the_background_and_swaps_only_on_check(self):
        reloader = self.make([2, 2])
        self.assertIsNone(reloader.check())
        reloader.thread.join(2)
        self.assertEqual(self.oracle.version, 1)
        self.assertIs(self.oracle.laya, self.old)
        self.assertEqual(reloader.check(), 2)
        self.assertEqual(self.logs[-1], "laya: reloaded fine-tuned weights v2")
        self.assertIs(self.oracle.laya, self.loaded[0])
        self.assertTrue(self.loaded[0].warmed)
        self.assertTrue(self.old.released)
        self.clock.now += 2
        self.assertIsNone(reloader.check())
        self.assertEqual(len(self.loaded), 1)

    def test_same_version_or_no_weights_does_nothing(self):
        reloader = self.make([1, None])
        reloader.check()
        self.clock.now += 2
        reloader.check()
        self.assertIsNone(reloader.thread)
        self.assertEqual(self.logs, [])

    def test_checks_are_throttled(self):
        reloader = self.make([1, 1, 1])
        reloader.check()
        reloader.check()
        self.clock.now += 2
        reloader.check()
        self.assertEqual(list(self.versions), [1])

    def test_failed_load_keeps_the_old_weights_and_is_not_retried(self):
        def broken(model):
            raise RuntimeError("half-written")

        reloader = self.make([3, 3], factory=broken)
        reloader.check()
        reloader.thread.join(2)
        self.clock.now += 2
        reloader.check()
        self.assertIs(self.oracle.laya, self.old)
        self.assertEqual(len([m for m in self.logs if "not reloaded" in m]), 1)
        self.assertIn("keeping the fine-tuned v1 weights", self.logs[0])

    def test_parked_weights_return_to_the_gpu_after_the_wait_limit(self):
        reloader = self.make([1, 1])
        self.assertTrue(reloader.park())
        self.assertTrue(self.old.parked)
        self.assertIn("parked on the CPU", self.logs[0])
        reloader.check()
        self.assertTrue(self.old.parked)
        self.clock.now += 61
        reloader.check()
        reloader.unparking.join(2)
        self.assertFalse(self.old.parked)
        self.assertFalse(self.oracle.parked)
        self.assertIn("back on the GPU", self.logs[-1])

    def test_next_match_unparks_and_new_weights_replace_parked_ones(self):
        reloader = self.make([2])
        reloader.park()
        reloader.resume()
        reloader.unparking.join(2)
        self.assertFalse(self.old.parked)
        reloader.park()
        reloader.check()
        reloader.thread.join(2)
        reloader.check()
        self.assertTrue(self.old.released)
        self.assertFalse(self.oracle.parked)
        self.assertIsNone(reloader.parked_at)


if __name__ == "__main__":
    unittest.main()
