import atexit
import ctypes
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "pad.json"
DIRECTIONS = ("n", "f", "b", "u", "d", "uf", "ub", "df", "db")
VIRTUAL_KEYS = {"PAUSE": 0x13, "SCROLL": 0x91, "F8": 0x77, "F9": 0x78, "F10": 0x79, "F12": 0x7B}
KEY_DOWN = 0x8000


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


class Pad:
    def __init__(self, config=None, device=None, codes=None, kill_key=True):
        self.config = config or load_config()
        self.device = device if device is not None else vgamepad_device()
        self.codes = codes if codes is not None else vgamepad_codes()
        self.held = set()
        self.kill = KillKey(self.config["kill_key"]) if kill_key else None
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

    def names_for(self, direction="n", buttons=(), side=0):
        names = {self.config["directions"][d] for d in absolute(direction, side)}
        names.update(self.config["buttons"][str(b)] for b in buttons)
        return names

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

    def apply(self, direction="n", buttons=(), side=0):
        return self.set_names(self.names_for(direction, buttons, side))

    def menu(self, keys):
        names = set()
        for key in keys:
            if key in ("u", "d"):
                names.add(self.config["directions"][key])
            elif key in ("l", "r"):
                names.add(self.config["directions"]["left" if key == "l" else "right"])
            else:
                names.add(self.config["menu"][key])
        return self.set_names(names)

    def release_all(self):
        try:
            self.device.reset()
            self.device.update()
        finally:
            self.held = set()

    def check_kill(self):
        if self.kill is not None and self.kill.pressed():
            self.release_all()
            raise KillSwitch(f"kill key {self.kill.name} pressed")
