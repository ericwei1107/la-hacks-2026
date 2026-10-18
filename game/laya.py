import os
import statistics
import threading
import time
from collections import OrderedDict
from pathlib import Path

from game.finetune import QUESTIONS, model_version

MODEL = "convaiinnovations/laya"
WARMUP_TEXT = "The opponent is standing at close range. The bot is healthy. It is early in the round. The stage is open."
LATENCY_KEEP = 500
FINETUNED_NAME = "laya-ft"
BENCH_ROUNDS = 50
CACHE_SIZE = 512
RELOAD_CHECK_S = 1.0
PARK_MAX_S = 60.0


def question_set(keys=None):
    return {k: {"type": "noul", "instructions": QUESTIONS[k]} for k in (keys or QUESTIONS)}


def hub_home():
    return Path(os.environ.get("HF_HUB_CACHE") or Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface") / "hub")


def hub_cached(model=MODEL):
    return (hub_home() / ("models--" + model.replace("/", "--"))).exists()


def has_weights(path):
    path = Path(path)
    return (path / "model.safetensors").exists() and (path / "rl_agent_config.json").exists()


def hub_snapshot(model=MODEL):
    repo = hub_home() / ("models--" + model.replace("/", "--"))
    ref = repo / "refs" / "main"
    if ref.exists():
        snap = repo / "snapshots" / ref.read_text(encoding="utf-8").strip()
        if has_weights(snap):
            return snap
    return None


def finetuned_dir():
    from game.recorder import data_dir
    return data_dir() / "models" / FINETUNED_NAME


def resolve_model():
    path = finetuned_dir()
    if has_weights(path):
        return str(path), "fine-tuned"
    return MODEL, "base"


def weights_label(version):
    return "base" if version is None else f"fine-tuned v{version}"


def current_version():
    path = finetuned_dir()
    return model_version(path) if has_weights(path) else None


def startup(log=print, rounds=BENCH_ROUNDS, factory=None, on_ready=None):
    model, kind = resolve_model()
    version = current_version() if kind == "fine-tuned" else None
    log(f"laya: loading {kind} weights from {model}" + (f" (v{version})" if version is not None else ""), flush=True)
    try:
        laya = (factory or Laya)(model)
        stats = laya.bench([WARMUP_TEXT], rounds)
    except (SystemExit, Exception) as e:
        log(f"laya: not loaded ({e}); the bot plays without it", flush=True)
        return None
    log(f"laya: {kind} weights loaded in {laya.load_seconds or 0.0:.1f} s; {len(QUESTIONS)}-question batch over {stats['n']} calls: "
        f"p50 {stats['p50_ms']} ms, p95 {stats['p95_ms']} ms", flush=True)
    if on_ready is not None:
        on_ready(laya, version)
    return laya


def start_background(log=print, rounds=BENCH_ROUNDS, factory=None, on_ready=None):
    thread = threading.Thread(target=startup, kwargs={"log": log, "rounds": rounds, "factory": factory, "on_ready": on_ready},
                              name="laya-load", daemon=True)
    thread.start()
    return thread


class Oracle:
    def __init__(self, laya=None, version=None, log=print, cache=CACHE_SIZE, threaded=True):
        self.laya = laya
        self.version = version
        self.log = log
        self.size = cache
        self.threaded = threaded
        self.cache = OrderedDict()
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.wanted = None
        self.closed = False
        self.failed = False
        self.parked = False
        self.thread = None

    @property
    def ready(self):
        return self.laya is not None

    def park(self):
        with self.lock:
            laya = self.laya
            if laya is None or not hasattr(laya, "park"):
                return False
            self.parked = True
            self.wanted = None
        if laya.park():
            return True
        with self.lock:
            if self.laya is laya:
                self.parked = False
        return False

    def unpark(self):
        with self.lock:
            laya = self.laya
        if laya is None:
            return False
        laya.unpark()
        with self.lock:
            if self.laya is laya:
                self.parked = False
        return True

    def start(self):
        if self.threaded and self.thread is None:
            self.thread = threading.Thread(target=self._run, name="laya-oracle", daemon=True)
            self.thread.start()
        return self

    def attach(self, laya, version=None):
        with self.lock:
            old = self.laya
            self.laya = laya
            self.version = version
            self.cache.clear()
            self.wanted = None
            self.failed = False
            self.parked = False
        if old is not None and old is not laya:
            old.release()

    def submit(self, text):
        if self.laya is None or self.parked or not text:
            return
        with self.lock:
            if text in self.cache or text == self.wanted:
                return
            self.wanted = text
        if self.threaded:
            self.wake.set()
        else:
            self._answer_wanted()

    def answer(self, text):
        with self.lock:
            return self.cache.get(text)

    def close(self):
        self.closed = True
        self.wake.set()

    def _answer_wanted(self):
        with self.lock:
            text, laya = self.wanted, self.laya
        if text is None or laya is None or self.parked:
            return False
        try:
            answers = laya.predict(text)
        except Exception as e:
            with self.lock:
                if self.wanted == text:
                    self.wanted = None
                first = not self.failed
                self.failed = True
            if first:
                self.log(f"laya: predict failed ({e!r}); those decisions fall back to habits", flush=True)
            return False
        with self.lock:
            if self.laya is laya:
                self.cache[text] = answers
                while len(self.cache) > self.size:
                    self.cache.popitem(last=False)
            if self.wanted == text:
                self.wanted = None
            return self.wanted is not None

    def _run(self):
        while not self.closed:
            self.wake.wait()
            self.wake.clear()
            while not self.closed and self._answer_wanted():
                pass


class Reloader:
    def __init__(self, oracle, log=print, factory=None, version_of=current_version, every=RELOAD_CHECK_S, clock=time.monotonic,
                 park_max=PARK_MAX_S):
        self.oracle = oracle
        self.park_max = park_max
        self.parked_at = None
        self.unparking = None
        self.log = log
        self.factory = factory or (lambda model: Laya(model).load())
        self.version_of = version_of
        self.every = every
        self.clock = clock
        self.last = None
        self.thread = None
        self.staged = None
        self.failed = None

    def _load(self, version):
        try:
            laya = self.factory(str(finetuned_dir()))
            laya.warmup()
        except (SystemExit, Exception) as e:
            self.failed = version
            self.log(f"laya: fine-tuned weights v{version} not reloaded ({e}); keeping the {weights_label(self.oracle.version)} weights", flush=True)
            return
        self.staged = (laya, version)

    def park(self):
        if self.oracle.park():
            self.parked_at = self.clock()
            self.log(f"laya: parked on the CPU until new fine-tuned weights land (at most {self.park_max:.0f} s), so the fine-tune has the GPU",
                     flush=True)
            return True
        return False

    def unpark(self):
        self.parked_at = None
        self.unparking = threading.Thread(target=self.oracle.unpark, name="laya-unpark", daemon=True)
        self.unparking.start()
        return self.unparking

    def resume(self):
        if self.parked_at is not None:
            self.unpark()
            self.log("laya: next match started; moving the current weights back to the GPU (habits answer until then)", flush=True)

    def check(self):
        if self.thread is not None and self.thread.is_alive():
            return None
        if self.staged is not None:
            laya, version = self.staged
            self.staged = None
            self.parked_at = None
            self.oracle.attach(laya, version)
            self.log(f"laya: reloaded fine-tuned weights v{version}", flush=True)
            return version
        now = self.clock()
        if self.last is not None and now - self.last < self.every:
            return None
        self.last = now
        if self.parked_at is not None and now - self.parked_at >= self.park_max:
            self.unpark()
            self.log(f"laya: no new fine-tuned weights after {self.park_max:.0f} s; {weights_label(self.oracle.version)} weights back on the GPU",
                     flush=True)
        if not self.oracle.ready:
            return None
        version = self.version_of()
        if version is None or version == self.oracle.version or version == self.failed:
            return None
        self.thread = threading.Thread(target=self._load, args=(version,), name="laya-reload", daemon=True)
        self.thread.start()
        return None


def empty_cuda():
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


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
        self.parked = False

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

    def park(self):
        model = getattr(self.agent, "model", None)
        if model is None or not hasattr(model, "to"):
            return False
        with self.lock:
            model.to("cpu")
            self.parked = True
        empty_cuda()
        return True

    def unpark(self):
        with self.lock:
            if not self.parked or self.agent is None:
                return False
            self.agent.model.to(self.agent.device)
            self.parked = False
        return True

    def release(self):
        with self.lock:
            self.agent = None
            self.parked = False
        empty_cuda()

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
