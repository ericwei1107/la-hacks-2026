import unittest
from types import SimpleNamespace

from game.latency import histogram, trial
from game.tests.test_pad import fake_pad

IDLE = 0x8001
JAB = 0x659


def snaps(start, change_at, held_at=None, move=JAB, jump_at=None):
    frame = start
    for dt in range(0, 40):
        f = start + dt if jump_at is None or dt < jump_at else start + dt + 5
        bot = {"side": 1, "move_id": move if dt >= change_at else IDLE,
               "game_buttons": (1 << 9) if held_at is not None and dt >= held_at else 0}
        yield SimpleNamespace(round_frame=f, players=[{}, bot]), (5 if jump_at is not None and dt == jump_at else 0)


class LatencyTrialTest(unittest.TestCase):
    def test_counts_round_frames_to_move_change(self):
        pad, device = fake_pad()
        lat, seen, why = trial(snaps(100, 3, held_at=1), pad, 1, JAB)
        self.assertEqual((lat, seen, why), (3, 1, None))
        self.assertEqual(device.pressed, set())

    def test_wrong_move_discarded(self):
        pad, _ = fake_pad()
        lat, _, why = trial(snaps(100, 2, move=0x645), pad, 1, JAB)
        self.assertIsNone(lat)
        self.assertIn("not the jab", why)

    def test_skipped_frames_discarded(self):
        pad, _ = fake_pad()
        lat, _, why = trial(snaps(100, 10, jump_at=2), pad, 1, JAB)
        self.assertIsNone(lat)
        self.assertIn("jumped", why)

    def test_timeout(self):
        pad, device = fake_pad()
        lat, _, why = trial(snaps(100, 99), pad, 1, JAB)
        self.assertIsNone(lat)
        self.assertEqual(device.pressed, set())

    def test_histogram(self):
        self.assertEqual(histogram([2, 2, 3]).splitlines()[0].split("|")[1].strip(), "## 2")


if __name__ == "__main__":
    unittest.main()
