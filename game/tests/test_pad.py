import random
import socket
import threading
import time
import unittest

from game.difficulty import PRESETS, Difficulty
from game.pad import Pad, RemotePad, absolute, load_config
from game.padserver import Server


class FakeDevice:
    def __init__(self):
        self.pressed = set()
        self.updates = 0
        self.resets = 0

    def press_button(self, button):
        self.pressed.add(button)

    def release_button(self, button):
        self.pressed.discard(button)

    def update(self):
        self.updates += 1

    def reset(self):
        self.pressed = set()
        self.resets += 1


def fake_pad():
    config = load_config()
    names = set(config["buttons"].values()) | set(config["directions"].values()) | set(config["menu"].values())
    device = FakeDevice()
    return Pad(config=config, device=device, codes={n: n for n in names}, kill_key=False), device


class AbsoluteTest(unittest.TestCase):
    def test_forward_flips_with_side(self):
        self.assertEqual(absolute("f", 0), {"right"})
        self.assertEqual(absolute("f", 1), {"left"})
        self.assertEqual(absolute("b", 0), {"left"})
        self.assertEqual(absolute("b", 1), {"right"})

    def test_diagonals(self):
        self.assertEqual(absolute("df", 0), {"d", "right"})
        self.assertEqual(absolute("db", 1), {"d", "right"})
        self.assertEqual(absolute("uf", 1), {"u", "left"})
        self.assertEqual(absolute("n", 0), set())

    def test_unknown_direction(self):
        with self.assertRaises(ValueError):
            absolute("fd", 0)


class PadTest(unittest.TestCase):
    def test_mapping_from_config(self):
        pad, device = fake_pad()
        pad.apply("df", ("1",), side=0)
        self.assertEqual(device.pressed, {"DPAD_DOWN", "DPAD_RIGHT", "X"})
        pad.apply("df", ("1",), side=1)
        self.assertEqual(device.pressed, {"DPAD_DOWN", "DPAD_LEFT", "X"})
        pad.apply("n", ("2", "3"), side=1)
        self.assertEqual(device.pressed, {"Y", "A"})

    def test_no_update_when_unchanged(self):
        pad, device = fake_pad()
        pad.apply("n", ("4",))
        before = device.updates
        self.assertFalse(pad.apply("n", ("4",)))
        self.assertEqual(device.updates, before)

    def test_release_all(self):
        pad, device = fake_pad()
        pad.apply("db", ("1", "2"))
        pad.release_all()
        self.assertEqual(device.pressed, set())
        self.assertEqual(pad.held, set())
        self.assertEqual(device.resets, 1)

    def test_release_on_exception(self):
        pad, device = fake_pad()
        try:
            try:
                pad.apply("f", ("1",))
                raise RuntimeError("boom")
            finally:
                pad.release_all()
        except RuntimeError:
            pass
        self.assertEqual(device.pressed, set())

    def test_menu_keys(self):
        pad, device = fake_pad()
        pad.menu(["r", "a"])
        self.assertEqual(device.pressed, {"DPAD_RIGHT", "A"})


class PadServerTest(unittest.TestCase):
    def setUp(self):
        self.pad, self.device = fake_pad()
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_sock.bind(("127.0.0.1", 0))
        config = dict(self.pad.config, server={"host": "127.0.0.1", "port": self.server_sock.getsockname()[1]})
        self.server = Server(self.pad, self.server_sock)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.server.serve, args=(self.stop,), daemon=True)
        self.thread.start()
        self.client = RemotePad(config, kill_key=False)

    def tearDown(self):
        self.stop.set()
        self.thread.join(1)
        self.server_sock.close()
        self.client.sock.close()

    def wait_for(self, predicate):
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.005)
        return False

    def test_hello_set_release(self):
        self.assertTrue(self.client.hello())
        self.client.apply("df", ("2",), side=1)
        self.assertTrue(self.wait_for(lambda: self.device.pressed == {"DPAD_DOWN", "DPAD_LEFT", "Y"}))
        self.client.release_all()
        self.assertTrue(self.wait_for(lambda: self.device.pressed == set()))

    def test_watchdog_releases_silent_client(self):
        self.client.apply("b")
        self.assertTrue(self.wait_for(lambda: self.device.pressed == {"DPAD_LEFT"}))
        self.server.last_message -= 10
        self.assertTrue(self.wait_for(lambda: self.device.pressed == set()))

    def test_hello_fails_without_server(self):
        self.stop.set()
        self.thread.join(1)
        self.server_sock.close()
        self.assertFalse(self.client.hello(timeout=0.1))


class DifficultyTest(unittest.TestCase):
    def test_presets_match_design_doc(self):
        self.assertEqual([PRESETS[i]["reaction_delay_frames"] for i in range(1, 6)], [30, 24, 18, 12, 6])
        self.assertEqual([PRESETS[i]["punish_accuracy"] for i in range(1, 6)], [0.40, 0.60, 0.80, 0.92, 1.0])
        self.assertEqual([PRESETS[i]["execution_error"] for i in range(1, 6)], [0.15, 0.10, 0.05, 0.02, 0.0])

    def test_knob_override(self):
        d = Difficulty.preset(3, {"reaction_delay_frames": 4, "unknown": 1})
        self.assertEqual(d.reaction_delay_frames, 4)
        self.assertEqual(d.punish_accuracy, 0.80)

    def test_reaction_draw(self):
        rng = random.Random(1)
        draws = [Difficulty.preset(1).reaction(rng) for _ in range(2000)]
        mean = sum(draws) / len(draws)
        self.assertTrue(28 <= mean <= 32)
        self.assertTrue(all(d >= 0 for d in draws))

    def test_frame_perfect_gives_zero(self):
        rng = random.Random(2)
        d = Difficulty.preset(5)
        zeros = sum(1 for _ in range(2000) if d.reaction(rng) == 0)
        self.assertTrue(0.35 <= zeros / 2000 <= 0.45)
        self.assertEqual(sum(1 for _ in range(500) if Difficulty.preset(1).reaction(rng) == 0), 0)


if __name__ == "__main__":
    unittest.main()
