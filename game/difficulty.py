from dataclasses import dataclass, fields, replace

REACTION_SD = 0.2

PRESETS = {
    1: {"reaction_delay_frames": 30, "frame_perfect_chance": 0.0, "punish_accuracy": 0.40, "exploit_weight": 0.2,
        "combo_set": "short", "movement_set": "basic", "mixup_temperature": 2.0, "execution_error": 0.15},
    2: {"reaction_delay_frames": 24, "frame_perfect_chance": 0.0, "punish_accuracy": 0.60, "exploit_weight": 0.4,
        "combo_set": "short", "movement_set": "sidestep", "mixup_temperature": 2.0, "execution_error": 0.10},
    3: {"reaction_delay_frames": 18, "frame_perfect_chance": 0.05, "punish_accuracy": 0.80, "exploit_weight": 0.6,
        "combo_set": "short_plus_optimal", "movement_set": "character", "mixup_temperature": 1.0, "execution_error": 0.05},
    4: {"reaction_delay_frames": 12, "frame_perfect_chance": 0.15, "punish_accuracy": 0.92, "exploit_weight": 0.8,
        "combo_set": "optimal", "movement_set": "full", "mixup_temperature": 1.0, "execution_error": 0.02},
    5: {"reaction_delay_frames": 6, "frame_perfect_chance": 0.40, "punish_accuracy": 1.0, "exploit_weight": 1.0,
        "combo_set": "optimal", "movement_set": "full", "mixup_temperature": 0.5, "execution_error": 0.0},
}


@dataclass(frozen=True)
class Difficulty:
    level: int
    reaction_delay_frames: int
    frame_perfect_chance: float
    punish_accuracy: float
    exploit_weight: float
    combo_set: str
    movement_set: str
    mixup_temperature: float
    execution_error: float

    @classmethod
    def preset(cls, level, knobs=None):
        if level not in PRESETS:
            raise ValueError(f"difficulty must be 1..5, got {level}")
        known = {f.name for f in fields(cls)}
        values = dict(PRESETS[level])
        values.update({k: v for k, v in (knobs or {}).items() if k in known and k != "level"})
        return cls(level=level, **values)

    def knobs(self):
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name != "level"}

    def with_knobs(self, **knobs):
        return replace(self, **knobs)

    def frame_perfect(self, rng):
        return rng.random() < self.frame_perfect_chance

    def reaction(self, rng):
        if self.frame_perfect(rng):
            return 0
        mean = self.reaction_delay_frames
        return max(0, round(rng.gauss(mean, mean * REACTION_SD)))

    def accurate(self, rng):
        return rng.random() < self.punish_accuracy
