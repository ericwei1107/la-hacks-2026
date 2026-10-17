import re
from dataclasses import dataclass, field

NEUTRAL = ("n", ())
DIRECTIONS = ("n", "f", "b", "u", "d", "uf", "ub", "df", "db")
MOTIONS = {
    "qcf": ("d", "df", "f"),
    "qcb": ("d", "db", "b"),
    "hcf": ("b", "db", "d", "df", "f"),
    "hcb": ("f", "df", "d", "db", "b"),
}
TOKEN = re.compile(
    r"^(?P<ws>ws\+?)?"
    r"(?P<motion>qcf|qcb|hcf|hcb)?"
    r"(?P<dir>[udUD]/?[fbFB]|[fbnFB]|[udUD])?"
    r"(?:\+?(?P<buttons>[1-4](?:\+[1-4])*))?$"
)
SPLIT = re.compile(r"\s*([,:])\s*")


@dataclass(frozen=True)
class Timing:
    press_frames: int = 2
    string_gap: int = 6
    hold_frames: int = 10
    ws_crouch_frames: int = 6
    ws_release_frames: int = 1

    @classmethod
    def from_config(cls, config):
        known = cls.__dataclass_fields__
        return cls(**{k: v for k, v in (config or {}).items() if k in known})


@dataclass(frozen=True)
class Step:
    direction: str = "n"
    buttons: tuple = ()
    hold: bool = False
    ws: bool = False
    motion: tuple = ()
    joiner: str = ","

    @property
    def has_buttons(self):
        return bool(self.buttons)


class NotationError(ValueError):
    pass


def normalize_direction(text):
    if not text:
        return "n", False
    hold = text.isupper()
    d = text.lower().replace("/", "")
    if d not in DIRECTIONS:
        raise NotationError(f"unknown direction {text!r}")
    return d, hold


def parse_token(text, joiner):
    m = TOKEN.match(text)
    if not m or not text:
        raise NotationError(f"cannot parse {text!r}")
    direction, hold = normalize_direction(m.group("dir"))
    buttons = tuple(sorted(set(m.group("buttons").split("+")))) if m.group("buttons") else ()
    ws = bool(m.group("ws"))
    motion = MOTIONS[m.group("motion")] if m.group("motion") else ()
    if ws and not buttons:
        raise NotationError(f"ws needs a button in {text!r}")
    if ws and (direction != "n" or motion):
        raise NotationError(f"ws takes only buttons in {text!r}")
    if motion and m.group("dir"):
        raise NotationError(f"motion and direction together in {text!r}")
    if motion:
        direction = motion[-1]
    if not buttons and not m.group("dir") and not motion:
        raise NotationError(f"empty step {text!r}")
    return Step(direction, buttons, hold, ws, motion, joiner)


def parse(text):
    text = text.strip()
    if not text:
        raise NotationError("empty notation")
    parts = SPLIT.split(text)
    steps = []
    joiner = ","
    for i, part in enumerate(parts):
        if i % 2:
            joiner = part
            continue
        steps.append(parse_token(part, joiner))
    return steps


def expand(step, timing):
    lead = []
    if step.ws:
        lead = [("d", ())] * timing.ws_crouch_frames + [NEUTRAL] * timing.ws_release_frames
    elif step.motion:
        lead = [(d, ()) for d in step.motion[:-1]]
    if step.hold:
        hold = max(1, timing.hold_frames - (timing.press_frames if step.buttons else 0))
        lead = lead + [(step.direction, ())] * hold
    if step.buttons:
        body = [(step.direction, step.buttons)] * timing.press_frames
    elif step.hold:
        body = []
    else:
        body = [(step.direction, ())]
    return lead, body


def to_frames(steps, timing=Timing()):
    out = {}
    prev_anchor = None
    prev_end = 0
    prev_buttons = False
    prev_last = NEUTRAL
    for step in steps:
        lead, body = expand(step, timing)
        masks = lead + body
        if prev_anchor is None:
            start = 0
        elif step.joiner == ":":
            start = prev_anchor + 1 - len(lead)
        elif step.has_buttons and prev_buttons and not lead:
            start = prev_anchor + timing.string_gap
        elif masks[0] == prev_last and prev_last != NEUTRAL:
            start = prev_end + 1
        else:
            start = prev_end
        start = max(start, 0)
        for i, mask in enumerate(masks):
            out[start + i] = mask
        prev_anchor = start + len(lead)
        prev_end = start + len(masks)
        prev_buttons = step.has_buttons
        prev_last = masks[-1]
    length = max(out) + 1 if out else 0
    return [out.get(i, NEUTRAL) for i in range(length)]


def compile_notation(text, timing=Timing()):
    return to_frames(parse(text), timing)


def runs(frames):
    out = []
    for mask in frames:
        if out and out[-1][0] == mask:
            out[-1][1] += 1
        else:
            out.append([mask, 1])
    return out


def token(direction, buttons, hold=False):
    d = direction.upper() if hold else direction
    if not buttons:
        return d
    return ("" if direction == "n" else d + "+") + "+".join(buttons)


def describe(frames, timing=Timing()):
    rs = runs(frames)
    tokens = []
    joiners = []
    i = 0
    gap_before = False
    while i < len(rs):
        (d, b), n = rs[i]
        nxt = rs[i + 1] if i + 1 < len(rs) else None
        after = rs[i + 2] if i + 2 < len(rs) else None
        if (d, b) == NEUTRAL:
            between_dirs = (tokens and nxt and n == 1 and not nxt[0][1] and not rs[i - 1][0][1]
                            and rs[i - 1][0] != nxt[0])
            if between_dirs:
                tokens.append("n")
                joiners.append(",")
            else:
                gap_before = True
            i += 1
            continue
        if (d == "d" and not b and n >= timing.ws_crouch_frames and nxt and nxt[0] == NEUTRAL
                and nxt[1] == timing.ws_release_frames and after and after[0][0] == "n" and after[0][1]):
            tokens.append("ws+" + "+".join(after[0][1]))
            joiners.append(",")
            gap_before = False
            i += 3
            continue
        if not b and n > 1 and nxt and nxt[0][0] == d and nxt[0][1]:
            tokens.append(token(d, nxt[0][1], hold=True))
            joiners.append(",")
            gap_before = False
            i += 2
            continue
        if not b and n > 1:
            tokens.append(token(d, (), hold=True))
            joiners.append(",")
            i += 1
            continue
        prev_had_buttons = i > 0 and bool(rs[i - 1][0][1])
        joiners.append(":" if b and prev_had_buttons and not gap_before else ",")
        tokens.append(token(d, b))
        gap_before = False
        i += 1
    text = ""
    for j, (t, joiner) in enumerate(zip(tokens, joiners)):
        text += t if j == 0 else joiner + t
    return text
