import random
from collections import deque
from dataclasses import dataclass, field

from game.notation import NEUTRAL, Timing, compile_notation

DELAY_SHARE = 2 / 3
MAX_ERROR_DELAY = 2


@dataclass
class Move:
    notation: str
    frames: list
    prepress: bool = False
    earliest: int | None = None
    tag: dict = field(default_factory=dict)
    error: str | None = None
    queued_frame: int | None = None
    start_frame: int | None = None
    done_frame: int | None = None
    cancelled: bool = False


def onsets(frames):
    out = []
    for i, mask in enumerate(frames):
        if mask != NEUTRAL and (i == 0 or frames[i - 1] != mask):
            out.append(i)
    return out


def apply_execution_error(frames, chance, rng):
    if chance <= 0 or rng.random() >= chance:
        return frames, None
    starts = onsets(frames)
    if not starts:
        return frames, None
    i = rng.choice(starts)
    before = frames[i - 1] if i > 0 else NEUTRAL
    if rng.random() < DELAY_SHARE:
        k = rng.randint(1, MAX_ERROR_DELAY)
        return frames[:i] + [before] * k + frames[i:], f"delayed input {i} by {k}"
    end = i
    while end < len(frames) and frames[end] == frames[i]:
        end += 1
    return frames[:i] + [before] * (end - i) + frames[end:], f"dropped input {i}"


class Sequencer:
    def __init__(self, pad, latency, difficulty=None, rng=None, timing=None):
        self.pad = pad
        self.latency = latency
        self.difficulty = difficulty
        self.rng = rng or random.Random()
        self.timing = timing or Timing()
        self.queue = deque()
        self.active = None
        self.background = NEUTRAL
        self.applied = []
        self.finished = []
        self.last_frame = None

    def submit(self, notation, prepress=False, earliest=None, frame=None, error=True, **tag):
        frames = compile_notation(notation, self.timing)
        move = Move(notation, frames, prepress, earliest, tag, queued_frame=frame)
        if error and self.difficulty is not None:
            move.frames, move.error = apply_execution_error(frames, self.difficulty.execution_error, self.rng)
        self.queue.append(move)
        return move

    def hold(self, direction="n", buttons=()):
        self.background = (direction, tuple(buttons))

    def busy(self):
        return self.active is not None or bool(self.queue)

    def cancel(self, frame=None):
        for move in ([self.active] if self.active else []) + list(self.queue):
            move.cancelled = True
            move.done_frame = frame
            self.finished.append(move)
        self.active = None
        self.queue.clear()
        self.background = NEUTRAL
        self.pad.release_all()

    def ready(self, move, frame, bot):
        if move.earliest is not None and frame < move.earliest:
            return False
        if bot["free_movement"]:
            return True
        return move.prepress and bot["frames_until_actionable"] <= self.latency

    def on_frame(self, frame, bot, live=True):
        if not live:
            if self.busy() or self.background != NEUTRAL or self.pad.held:
                self.cancel(frame)
            self.last_frame = frame
            return None
        if self.last_frame is not None and frame < self.last_frame:
            self.cancel(frame)
        self.last_frame = frame
        mask = None
        if self.active is not None:
            idx = frame - self.active.start_frame
            if idx < len(self.active.frames):
                mask = self.active.frames[idx]
            else:
                self.active.done_frame = frame
                self.finished.append(self.active)
                self.active = None
        if self.active is None and self.queue and self.ready(self.queue[0], frame, bot):
            self.active = self.queue.popleft()
            self.active.start_frame = frame
            mask = self.active.frames[0] if self.active.frames else NEUTRAL
        if mask is None:
            mask = self.background
        if self.pad.apply(mask[0], mask[1], bot["side"]):
            self.applied.append((frame, mask))
        return mask

    def pop_finished(self):
        out, self.finished = self.finished, []
        return out
