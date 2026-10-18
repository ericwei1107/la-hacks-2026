import math
import os
import subprocess
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path

ENVIRONMENT = "demo-laptop"
SAMPLE_RATE = 0.05
FRAME_MS = 1000 / 60
ROOT = Path(__file__).resolve().parent.parent

_sdk = None
_current = None


def git_release(root=ROOT):
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and sha else "unknown"


def init(environ=None, sample_rate=SAMPLE_RATE, **options):
    global _sdk
    dsn = (os.environ if environ is None else environ).get("SENTRY_DSN")
    if not dsn:
        return "sentry: tracing off (SENTRY_DSN not set)"
    try:
        import sentry_sdk
    except ImportError:
        return "sentry: tracing off (sentry-sdk not installed; pip install -r game/requirements.txt)"
    release = git_release()
    try:
        sentry_sdk.init(dsn=dsn, release=release, environment=ENVIRONMENT, traces_sample_rate=sample_rate,
                        auto_enabling_integrations=False, **options)
    except Exception:
        return "sentry: tracing off (SENTRY_DSN rejected by the SDK)"
    _sdk = sentry_sdk
    return f"sentry: tracing on, release {release}, environment {ENVIRONMENT}, {sample_rate:.0%} of frames"


def enabled():
    return _sdk is not None


def close():
    global _sdk, _current
    if _sdk is not None:
        _sdk.get_client().close()
    _sdk = None
    _current = None


class Mark:
    def __init__(self):
        self.yielded = False
        self.complete = False


def _start():
    if _sdk is None:
        return None
    txn = _sdk.start_transaction(op="decision", name="game.decision")
    return txn if txn.sampled else None


@contextmanager
def decision(timer=None):
    global _current
    start = time.perf_counter()
    mark = Mark()
    txn = _start()
    try:
        if txn is None:
            yield mark
            return
        txn.__enter__()
        _current = txn
        status = "ok"
        try:
            yield mark
        except GeneratorExit:
            status = "cancelled"
            raise
        except BaseException:
            status = "internal_error"
            raise
        finally:
            _current = None
            if not mark.yielded:
                txn.sampled = False
            txn.set_status(status)
            txn.__exit__(None, None, None)
    finally:
        if timer is not None and mark.complete:
            timer.add(time.perf_counter() - start)


def span(op):
    if _current is None:
        return nullcontext()
    return _sdk.start_span(op=op, name=f"game.{op}")


def data(**values):
    if _current is not None:
        for key, value in values.items():
            _current.set_data(key, value)


def percentile(ordered, q):
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))]


class FrameTimer:
    def __init__(self):
        self.samples = []

    def add(self, seconds):
        self.samples.append(seconds)

    def stats(self):
        ordered = sorted(s * 1000 for s in self.samples)
        return {"count": len(ordered), "p50": percentile(ordered, 0.50), "p95": percentile(ordered, 0.95),
                "max": ordered[-1] if ordered else 0.0, "overruns": sum(1 for s in ordered if s > FRAME_MS)}

    def summary(self, missed):
        s = self.stats()
        return (f"timing ({'tracing on' if enabled() else 'tracing off'}): {s['count']} frame iterations, "
                f"p50 {s['p50']:.3f} ms, p95 {s['p95']:.3f} ms, max {s['max']:.3f} ms, "
                f"{s['overruns']} over {FRAME_MS:.1f} ms, {missed} missed frames")
