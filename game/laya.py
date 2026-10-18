import os
import statistics
import threading
import time
from pathlib import Path

from game.finetune import QUESTIONS

MODEL = "convaiinnovations/laya"
WARMUP_TEXT = "The opponent is standing at close range. The bot is healthy. It is early in the round. The stage is open."
LATENCY_KEEP = 500


def question_set(keys=None):
    return {k: {"type": "noul", "instructions": QUESTIONS[k]} for k in (keys or QUESTIONS)}


def hub_cached(model=MODEL):
    home = Path(os.environ.get("HF_HUB_CACHE") or Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface") / "hub")
    return (home / ("models--" + model.replace("/", "--"))).exists()


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


class FakeAgent:
    def __init__(self, answer=None, delay=0.0):
        self.answer = answer
        self.delay = delay
        self.calls = []
        self.warmed = 0

    def warmup(self):
        self.warmed += 1

    def _one(self, state, questions):
        self.calls.append((state, tuple(questions)))
        if self.delay:
            time.sleep(self.delay)
        answers = {}
        for key in questions:
            p = self.answer(state, key) if callable(self.answer) else (0.5 if self.answer is None else float(self.answer))
            answers[key] = {"noul": p, "confidence": abs(p - 0.5) * 2}
        return {"answers": answers, "routing": {"model": "fake"}}

    def predict(self, state, questions, **kwargs):
        return self._one(state, questions)

    def predict_batch(self, states, questions, batch_size=64, sort_by_length=True, **kwargs):
        return [self._one(s, questions) for s in states]


class Laya:
    def __init__(self, model=MODEL, device=None, agent=None, offline=None):
        self.model = model
        self.device = device
        self.agent = agent
        self.offline = offline
        self.lock = threading.Lock()
        self.latencies = []
        self.load_seconds = None
        self.warmup_seconds = None

    @property
    def loaded(self):
        return self.agent is not None

    def load(self):
        if self.agent is not None:
            return self
        local = Path(self.model).is_dir()
        offline = self.offline if self.offline is not None else (local or hub_cached(self.model))
        if offline:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("USE_TF", "0")
        try:
            import laya
        except ImportError as e:
            raise SystemExit(f"the laya package is not installed ({e}); run: pip install laya  (first load downloads about 808 MB "
                             f"from huggingface.co/{MODEL}; after that HF_HUB_OFFLINE=1 is set automatically)")
        started = time.perf_counter()
        kwargs = {"device": self.device} if self.device else {}
        self.agent = laya.load(self.model, **kwargs)
        self.load_seconds = time.perf_counter() - started
        return self

    def warmup(self, rounds=2):
        self.load()
        started = time.perf_counter()
        with self.lock:
            if hasattr(self.agent, "warmup"):
                self.agent.warmup()
            for _ in range(rounds):
                self.agent.predict(WARMUP_TEXT, question_set())
        self.warmup_seconds = time.perf_counter() - started
        return self.warmup_seconds

    @staticmethod
    def _answers(result, questions):
        answers = result.get("answers", {}) if isinstance(result, dict) else {}
        out = {}
        for key in questions:
            row = answers.get(key) or {}
            p = row.get("noul")
            out[key] = {"p": None if p is None else float(p), "confidence": row.get("confidence")}
        return out

    def predict(self, state_text, questions=None):
        questions = questions or question_set()
        self.load()
        started = time.perf_counter()
        with self.lock:
            result = self.agent.predict(state_text, questions)
        elapsed = time.perf_counter() - started
        self.latencies.append(elapsed)
        del self.latencies[:-LATENCY_KEEP]
        return self._answers(result, questions)

    def predict_batch(self, states, questions=None, batch_size=16):
        questions = questions or question_set()
        if not states:
            return []
        self.load()
        with self.lock:
            if hasattr(self.agent, "predict_batch"):
                results = self.agent.predict_batch(list(states), questions, batch_size=batch_size, sort_by_length=True)
            else:
                results = [self.agent.predict(s, questions) for s in states]
        return [self._answers(r, questions) for r in results]

    def latency(self):
        ms = [v * 1000 for v in self.latencies]
        if not ms:
            return {"n": 0, "p50_ms": None, "p95_ms": None, "mean_ms": None}
        return {"n": len(ms), "p50_ms": round(percentile(ms, 0.5), 2), "p95_ms": round(percentile(ms, 0.95), 2),
                "mean_ms": round(statistics.fmean(ms), 2)}

    def bench(self, texts, rounds=50):
        self.warmup()
        self.latencies = []
        for i in range(rounds):
            self.predict(texts[i % len(texts)])
        return self.latency()
