import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import sentry_sdk
from sentry_sdk.transport import Transport

from game import trace
from game.bot import BotHooks
from game.hotloop import run_session
from game.tests.test_hotloop import FakeReader
from game.tests.test_state import idle

DSN = "https://0123456789abcdef0123456789abcdef@o1.ingest.example.invalid/4512273716281344"
OPS = ["read", "decode", "reflex", "tactical", "input"]


class FakeTransport(Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.envelopes = []

    def capture_envelope(self, envelope):
        self.envelopes.append(envelope)

    def flush(self, timeout, callback=None):
        pass

    def kill(self):
        pass

    def transactions(self):
        return [item.payload.json for env in self.envelopes for item in env.items if item.type == "transaction"]


class Stub:
    def __init__(self, **returns):
        self.returns = returns

    def __getattr__(self, name):
        value = self.returns.get(name)
        return lambda *a, **k: list(value) if isinstance(value, list) else value


class StubPad:
    def check_kill(self):
        pass

    def release_all(self):
        pass


class StubBotHooks(BotHooks):
    def start(self, snap, sid):
        self.reflex = Stub(step=[], live=False)
        self.detector = Stub(step=[])
        self.learning = Stub(step=[])
        self.tactical = Stub(step=[])
        self.seq = Stub()


def session(tmp, frames=30, timing=False):
    args = SimpleNamespace(bot="kazuya", player="trace", difficulty=3, mode="practice", stage=None, rounds_to_win=None,
                           timing=timing)
    out = io.StringIO()
    with mock.patch.dict(os.environ, {"DATA_DIR": tmp}), redirect_stdout(out):
        run_session(FakeReader([(f, [idle(0, f), idle(1, f)]) for f in range(1, frames + 1)]), args,
                    StubBotHooks(StubPad(), None, config={"input_latency_frames": 2, "kill_key": "pause"}))
    records = [json.loads(line) for p in Path(tmp, "recordings").glob("*.jsonl")
               for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    return records, out.getvalue()


def shape(records):
    return [(r.get("t"), r.get("frame"), r.get("kind")) for r in records if r.get("t") != "session"]


class TraceTest(unittest.TestCase):
    def tearDown(self):
        trace.close()

    def traced(self, sample_rate=1.0):
        transport = FakeTransport()
        message = trace.init({"SENTRY_DSN": DSN}, sample_rate=sample_rate, transport=transport, default_integrations=False)
        self.assertTrue(trace.enabled(), message)
        return transport, message

    def test_no_dsn_never_initialises_the_sdk(self):
        with mock.patch.object(sentry_sdk, "init") as init:
            message = trace.init({})
        init.assert_not_called()
        self.assertFalse(trace.enabled())
        self.assertIn("off", message)
        with trace.decision() as mark:
            with trace.span("read") as s:
                self.assertIsNone(s)
        self.assertFalse(mark.complete)

    def test_tracing_off_and_on_record_the_same_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            off, _ = session(tmp)
        transport, _ = self.traced()
        with tempfile.TemporaryDirectory() as tmp:
            on, _ = session(tmp)
        self.assertEqual(shape(off), shape(on))
        self.assertEqual(sum(1 for r in on if r.get("t") == "state"), 30)
        self.assertTrue(transport.transactions())

    def test_five_spans_under_one_decision_transaction(self):
        transport, message = self.traced()
        self.assertIn(trace.ENVIRONMENT, message)
        with tempfile.TemporaryDirectory() as tmp:
            session(tmp, frames=10)
        txns = transport.transactions()
        self.assertEqual(len(txns), 10)
        for i, txn in enumerate(txns, start=1):
            ctx = txn["contexts"]["trace"]
            self.assertEqual((txn["transaction"], ctx["op"]), ("game.decision", "decision"))
            self.assertEqual(txn["environment"], "demo-laptop")
            self.assertEqual(txn["release"], trace.git_release())
            self.assertEqual(sorted(s["op"] for s in txn["spans"]), sorted(OPS))
            self.assertTrue(all(s["parent_span_id"] == ctx["span_id"] for s in txn["spans"]))
            self.assertTrue(all(s["trace_id"] == ctx["trace_id"] for s in txn["spans"]))
            self.assertEqual((ctx["data"]["frame"], ctx["data"]["round"]), (i, 1))
            self.assertNotIn("frame", txn.get("tags", {}))

    def test_unsampled_frames_send_nothing(self):
        transport, _ = self.traced(sample_rate=0.0)
        with tempfile.TemporaryDirectory() as tmp:
            session(tmp, frames=10)
        self.assertEqual(transport.transactions(), [])

    def test_exception_in_the_hook_still_finishes_the_transaction(self):
        transport, _ = self.traced()

        class Boom(StubBotHooks):
            def frame(self, state, events):
                super().frame(state, events)
                if state["frame"] == 3:
                    raise RuntimeError("boom")
                return []

        args = SimpleNamespace(bot="kazuya", player="trace", difficulty=3, mode="practice", stage=None, rounds_to_win=None)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"DATA_DIR": tmp}), redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):
                run_session(FakeReader([(f, [idle(0, f), idle(1, f)]) for f in range(1, 11)]), args,
                            Boom(StubPad(), None, config={"input_latency_frames": 2, "kill_key": "pause"}))
        txns = transport.transactions()
        self.assertEqual(len(txns), 3)
        self.assertEqual(txns[-1]["contexts"]["trace"]["status"], "cancelled")
        self.assertIsNone(trace._current)

    def test_dsn_never_written_or_printed(self):
        transport, message = self.traced()
        self.assertNotIn(DSN, message)
        with tempfile.TemporaryDirectory() as tmp:
            _, out = session(tmp, timing=True)
            written = [p.read_bytes() for p in Path(tmp).rglob("*") if p.is_file()]
        self.assertTrue(written)
        for blob in written:
            self.assertNotIn(DSN.encode(), blob)
            self.assertNotIn(b"0123456789abcdef0123456789abcdef", blob)
        self.assertNotIn("0123456789abcdef0123456789abcdef", out)

    def test_timing_prints_count_and_percentiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, out = session(tmp, frames=20, timing=True)
        line = next(l for l in out.splitlines() if l.startswith("timing"))
        self.assertIn("tracing off", line)
        self.assertIn("20 frame iterations", line)
        for key in ("p50", "p95", "max", "missed frames"):
            self.assertIn(key, line)

    def test_percentile_nearest_rank(self):
        ordered = list(range(1, 101))
        self.assertEqual(trace.percentile(ordered, 0.5), 50)
        self.assertEqual(trace.percentile(ordered, 0.95), 95)
        self.assertEqual(trace.percentile([7.0], 0.95), 7.0)
        self.assertEqual(trace.percentile([], 0.5), 0.0)


if __name__ == "__main__":
    unittest.main()
