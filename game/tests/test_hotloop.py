import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from game.hotloop import Hooks, run_session
from game.tests.test_state import idle


class FakeReader:
    def __init__(self, frames):
        self.script = iter(frames)
        self.cur = None
        self.game = {"version": "3.02.02"}
        self.discarded_health = 0
        self.torn_rereads = 0

    def poll_round_frame(self):
        try:
            self.cur = next(self.script)
        except StopIteration:
            raise KeyboardInterrupt
        return self.cur[0]

    def snapshot(self):
        f, players = self.cur if self.cur else (0, [idle(0, 0), idle(1, 0)])
        return SimpleNamespace(players=players, human_slot=0, round_frame=f)

    def resolve_blocks(self):
        pass

    def resolve_human(self):
        pass


class SpyHooks(Hooks):
    def __init__(self):
        self.order = []
        self.finished = []

    def frame(self, state, events):
        return []

    def finish(self, state, events):
        self.order.append("finish")
        self.finished += [(e["kind"], (e.get("detail") or {}).get("reason")) for e in events]
        return [{"t": "learning_event", "session_id": state["session_id"], "round": state["round"], "frame": state["frame"],
                 "event": "from_finish"}]

    def close(self):
        self.order.append("close")


class StopTest(unittest.TestCase):
    def test_stop_releases_the_pad_before_the_final_save_and_records_it(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"DATA_DIR": tmp}):
            hooks = SpyHooks()
            args = SimpleNamespace(bot="kazuya", player="stop", difficulty=3, mode="practice", stage=None, rounds_to_win=None)
            run_session(FakeReader([(f, [idle(0, f), idle(1, f)]) for f in range(1, 31)]), args, hooks)
            self.assertEqual(hooks.order, ["close", "finish"])
            self.assertEqual(hooks.finished, [("round_end", "stop")])
            recording = next(Path(tmp, "recordings").glob("*.jsonl"))
            records = [json.loads(line) for line in recording.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertTrue(any(r.get("t") == "learning_event" and r.get("event") == "from_finish" for r in records))
            self.assertEqual([r["kind"] for r in records if r.get("t") == "event"], ["round_start", "round_end"])


if __name__ == "__main__":
    unittest.main()
