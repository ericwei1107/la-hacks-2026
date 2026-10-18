import json
import tempfile
import threading
import unittest
from pathlib import Path

from game.finetune import QUESTIONS, build, evaluate, laya_row, majority_baseline, read_rows, write_laya
from game.laya import FakeAgent, Laya, percentile, question_set

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"


class HarnessTest(unittest.TestCase):
    def test_question_set_matches_design_9_4(self):
        qs = question_set()
        self.assertEqual(set(qs), {"opp_presses", "opp_ducks", "opp_steps", "opp_passive"})
        for q in qs.values():
            self.assertEqual(q["type"], "noul")
            self.assertTrue(q["instructions"].endswith("?"))
        self.assertEqual(list(question_set(["opp_ducks"])), ["opp_ducks"])

    def test_predict_shape_lock_and_latency(self):
        agent = FakeAgent(answer=lambda text, key: 0.9 if key == "opp_ducks" else 0.1, delay=0.001)
        model = Laya(agent=agent)
        self.assertTrue(model.loaded)
        model.warmup()
        self.assertEqual(agent.warmed, 1)
        out = model.predict("The opponent is crouching at close range.")
        self.assertEqual(set(out), set(QUESTIONS))
        self.assertAlmostEqual(out["opp_ducks"]["p"], 0.9)
        self.assertAlmostEqual(out["opp_presses"]["p"], 0.1)
        self.assertIn("confidence", out["opp_ducks"])
        stats = model.latency()
        self.assertEqual(stats["n"], 1)
        self.assertGreater(stats["p50_ms"], 0)
        self.assertGreaterEqual(stats["p95_ms"], stats["p50_ms"])
        seen = []
        original = agent.predict

        def guarded(state, questions, **kw):
            self.assertTrue(model.lock.locked())
            seen.append(state)
            return original(state, questions)

        agent.predict = guarded
        threads = [threading.Thread(target=model.predict, args=(f"state {i}",)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(seen), 6)
        batch = model.predict_batch(["a", "b", "c"])
        self.assertEqual(len(batch), 3)
        self.assertTrue(all(set(b) == set(QUESTIONS) for b in batch))
        self.assertEqual(model.predict_batch([]), [])

    def test_bench_reports_percentiles(self):
        model = Laya(agent=FakeAgent(answer=0.5))
        stats = model.bench(["x", "y"], rounds=20)
        self.assertEqual(stats["n"], 20)
        self.assertIsNotNone(stats["p95_ms"])
        self.assertEqual(percentile([1, 2, 3, 4], 0.5), 2.5)
        self.assertEqual(percentile([5], 0.95), 5)

    def test_missing_answer_is_none(self):
        class Odd(FakeAgent):
            def predict(self, state, questions, **kw):
                return {"answers": {"opp_ducks": {"noul": 0.7}}}

        out = Laya(agent=Odd()).predict("text")
        self.assertAlmostEqual(out["opp_ducks"]["p"], 0.7)
        self.assertIsNone(out["opp_presses"]["p"])


class FinetuneFormatTest(unittest.TestCase):
    def test_laya_rows_and_eval(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows, _, chosen, out = build([str(SAMPLES)], "versus_djin_vs_kaz_l3_neutral.zip", Path(tmp) / "set.jsonl")
            paths = write_laya(rows, tmp)
            train = read_rows(paths["train"])
            held = read_rows(paths["heldout"])
            self.assertEqual(len(train) + len(held), len(rows))
            self.assertEqual(len(held), sum(1 for r in rows if r["split"] == "heldout"))
            for row in held[:5] + train[:1]:
                self.assertEqual(set(row), {"state", "questions", "expected"})
                self.assertTrue(row["state"])
                for q, spec in row["questions"].items():
                    self.assertEqual(spec, {"type": "noul", "instructions": QUESTIONS[q]})
                    self.assertIsInstance(row["expected"][q], bool)
            self.assertEqual(laya_row(rows[0])["expected"], {q: bool(v) for q, v in rows[0]["questions"].items()})
            oracle = Laya(agent=FakeAgent(answer=lambda text, key: 1.0))
            result = evaluate(oracle, rows)
            self.assertEqual(result["opp_ducks"]["accuracy"], 0.0)
            self.assertEqual(result["opp_ducks"]["n"], sum(1 for r in rows if r["split"] == "heldout" and "opp_ducks" in r["questions"]))
            labels = {r["text"]: r["questions"] for r in rows}
            perfect = Laya(agent=FakeAgent(answer=lambda text, key: 1.0 if labels[text].get(key) else 0.0))
            result = evaluate(perfect, rows)
            self.assertGreaterEqual(result["overall"]["accuracy"], 0.95)
            for q in QUESTIONS:
                self.assertGreaterEqual(result[q]["accuracy"], 0.9)
            majority = majority_baseline(rows)
            constant = Laya(agent=FakeAgent(answer=lambda text, key: 0.0))
            result = evaluate(constant, rows)
            self.assertEqual(result["opp_ducks"]["accuracy"], 1.0)
            self.assertTrue(all(majority[q]["accuracy"] is None for q in QUESTIONS if q != "opp_ducks"))
            self.assertEqual(evaluate(constant, [r for r in rows if r["split"] == "train"]), {})


if __name__ == "__main__":
    unittest.main()
