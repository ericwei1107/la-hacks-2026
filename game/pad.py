import atexit
import ctypes
import json
import socket
import time
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "pad.json"
DIRECTIONS = ("n", "f", "b", "u", "d", "uf", "ub", "df", "db")
VIRTUAL_KEYS = {"PAUSE": 0x13, "SCROLL": 0x91, "F8": 0x77, "F9": 0x78, "F10": 0x79, "F12": 0x7B}
KEY_DOWN = 0x8000
HELLO_TIMEOUT_S = 0.3
KEEPALIVE_S = 0.5


class KillSwitch(Exception):
    pass


def load_config(path=CONFIG_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_config(config, path=CONFIG_PATH):
    Path(path).write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def absolute(direction, side):
    if direction not in DIRECTIONS:
        raise ValueError(f"unknown direction {direction!r}")
    out = set()
    if "u" in direction:
        out.add("u")
    if "d" in direction:
        out.add("d")
    toward, away = ("right", "left") if side == 0 else ("left", "right")
    if "f" in direction:
        out.add(toward)
    if "b" in direction:
        out.add(away)
    return out


def vgamepad_codes():
    import vgamepad as vg
    return {name.removeprefix("XUSB_GAMEPAD_"): getattr(vg.XUSB_BUTTON, name)
            for name in dir(vg.XUSB_BUTTON) if name.startswith("XUSB_GAMEPAD_")}


def vgamepad_device():
    import vgamepad as vg
    return vg.VX360Gamepad()


class KillKey:
    def __init__(self, name):
        self.name = name
        self.vk = VIRTUAL_KEYS[name]
        self.user32 = ctypes.windll.user32
        self.user32.GetAsyncKeyState(self.vk)

    def pressed(self):
        return bool(self.user32.GetAsyncKeyState(self.vk) & KEY_DOWN)


class Controls:
    def __init__(self, config=None, kill_key=True):
        self.config = config or load_config()
        self.held = set()
        self.kill = KillKey(self.config["kill_key"]) if kill_key else None

    def names_for(self, direction="n", buttons=(), side=0):
        names = {self.config["directions"][d] for d in absolute(direction, side)}
        names.update(self.config["buttons"][str(b)] for b in buttons)
        return names

    def menu_names(self, keys):
        names = set()
        for key in keys:
            if key in ("u", "d"):
                names.add(self.config["directions"][key])
            elif key in ("l", "r"):
                names.add(self.config["directions"]["left" if key == "l" else "right"])
            else:
                names.add(self.config["menu"][key])
        return names

    def apply(self, direction="n", buttons=(), side=0):
        return self.set_names(self.names_for(direction, buttons, side))

    def menu(self, keys):
        return self.set_names(self.menu_names(keys))

    def check_kill(self):
        if self.kill is not None and self.kill.pressed():
            self.release_all()
            raise KillSwitch(f"kill key {self.kill.name} pressed")


class Pad(Controls):
    remote = False

    def __init__(self, config=None, device=None, codes=None, kill_key=True):
        super().__init__(config, kill_key)
        self.device = device if device is not None else vgamepad_device()
        self.codes = codes if codes is not None else vgamepad_codes()
        self._console_handler = None
        atexit.register(self.release_all)
        if device is None:
            self._install_console_handler()

    def _install_console_handler(self):
        routine = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)

        def handler(_event):
            self.release_all()
            return 0

        self._console_handler = routine(handler)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(self._console_handler, True)

    def set_names(self, names):
        names = set(names)
        if names == self.held:
            return False
        for name in self.held - names:
            self.device.release_button(button=self.codes[name])
        for name in names - self.held:
            self.device.press_button(button=self.codes[name])
        self.held = names
        self.device.update()
        return True

    def release_all(self):
        try:
            self.device.reset()
            self.device.update()
        finally:
            self.held = set()


class RemotePad(Controls):
    remote = True

    def __init__(self, config=None, kill_key=True, sock=None):
        super().__init__(config, kill_key)
        server = self.config["server"]
        self.address = (server["host"], server["port"])
        self.sock = sock or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.last_send = 0.0
        atexit.register(self.release_all)

    def send(self, message):
        self.sock.sendto(json.dumps(message).encode(), self.address)
        self.last_send = time.monotonic()

    def hello(self, timeout=HELLO_TIMEOUT_S):
        self.sock.settimeout(timeout)
        try:
            self.send({"op": "hello"})
            data, _ = self.sock.recvfrom(4096)
            return json.loads(data).get("ok") is True
        except (OSError, ValueError):
            return False
        finally:
            self.sock.settimeout(None)

    def set_names(self, names):
        names = set(names)
        if names == self.held:
            return False
        self.send({"op": "set", "names": sorted(names)})
        self.held = names
        return True

    def release_all(self):
        try:
            self.send({"op": "release"})
        except OSError:
            pass
        finally:
            self.held = set()

    def check_kill(self):
        super().check_kill()
        if time.monotonic() - self.last_send >= KEEPALIVE_S:
            self.send({"op": "ping"})


def connect_pad(config=None, kill_key=True, log=print):
    remote = RemotePad(config, kill_key)
    if remote.hello():
        log(f"using padserver on {remote.address[0]}:{remote.address[1]} (pad stays plugged in after this exits)")
        return remote
    remote.sock.close()
    log("no padserver running: plugging in a new virtual pad for this run only. Tekken may need Start pressed on it, "
        "and may pause when it unplugs on exit. Run python -m game.padserver in another terminal to avoid that.")
    return Pad(config, kill_key=kill_key)
