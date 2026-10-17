import argparse
import json
import random
from pathlib import Path

from store import ROOT, check, data_dir

FPS = 60
IDLE = 0x8001
CROUCH = 0x8002
DOWNED = 0x80
HUMAN, BOT = 0, 1
CHAR = {HUMAN: ("devil_jin", 12), BOT: ("kazuya", 8)}
BUCKETS = ((1100, "point_blank"), (1600, "close"), (2500, "mid"), (3500, "far"))
STARTED = "2026-10-17T13:05:00Z"
STAMP = "2026-10-17T13-05-00"

MOVES = {
    "kaz_df1": {"id": 0x6A6, "level": "mid", "first": 15, "last": 16, "total": 41, "damage": 11, "block": -7, "hit": 9},
    "kaz_d4": {"id": 0x6DB, "level": "low", "first": 12, "last": 12, "total": 46, "damage": 12, "block": -12, "hit": 2},
    "kaz_df2": {"id": 0x6AF, "level": "mid", "first": 14, "last": 14, "total": 46, "damage": 22, "block": -12, "hit": 5},
    "kaz_throw": {"id": 0x71B, "level": "throw", "first": 12, "last": 14, "total": 45, "damage": 35},
    "dj_jab": {"id": 0x643, "level": "high", "first": 10, "last": 10, "total": 27, "damage": 5, "block": 1, "hit": 8},
    "dj_df1": {"id": 0x69B, "level": "mid", "first": 13, "last": 13, "total": 38, "damage": 12, "block": -1, "hit": 4},
}

SCRIPT = {
    1: [(120, "low", "hit"), (420, "low", "hit"), (700, "throw", "taken"), (900, "low", "hit"), (1150, "low", "blocked"), (1400, "low", "hit"), (1600, "throw", "broken")],
    2: [(120, "low", "hit"), (380, "low", "blocked"), (640, "mid", "duck"), (900, "low", "hit"), (1150, "low", "blocked"), (1400, "low", "hit"), (1600, "jab", "hit")],
    3: [(120, "low", "blocked"), (330, "low", "blocked"), (540, "low", "blocked"), (760, "mid", "blocked"), (980, "low", "blocked"), (1180, "throw", "broken"), (1380, "low", "blocked"), (1600, "jab", "hit")],
}

LEARNING = {
    1: {"prediction_accuracy": 0.41, "player_changed": False,
        "habits": {"low_defense": {"p": 0.8, "n": 5, "mastery": 0.22, "fixed": False}, "after_block:df1": {"p": 0.86, "n": 7, "mastery": 0.2, "fixed": False}, "throw_break": {"p": 0.5, "n": 2, "mastery": 0.35, "fixed": False}},
        "bandit": {"after_block:df1|block_high": {"low": 0.7, "mid": 0.3}}},
    2: {"prediction_accuracy": 0.58, "player_changed": False,
        "habits": {"low_defense": {"p": 0.7, "n": 10, "mastery": 0.55, "fixed": False}, "after_block:df1": {"p": 0.75, "n": 13, "mastery": 0.31, "fixed": False}, "throw_break": {"p": 0.5, "n": 2, "mastery": 0.38, "fixed": False}},
        "bandit": {"after_block:df1|block_high": {"low": 0.72, "mid": 0.28}, "after_block:df1|duck": {"mid": 0.8, "throw": 0.2}}},
    3: {"prediction_accuracy": 0.71, "player_changed": True,
        "habits": {"low_defense": {"p": 0.47, "n": 15, "mastery": 0.88, "fixed": True}, "after_block:df1": {"p": 0.6, "n": 20, "mastery": 0.62, "fixed": False}, "throw_break": {"p": 0.67, "n": 3, "mastery": 0.6, "fixed": False}},
        "bandit": {"after_block:df1|block_high": {"low": 0.3, "mid": 0.7}, "after_block:df1|duck": {"mid": 0.8, "throw": 0.2}}},
}

PLANS = {
    1: (0, {"aggression": 0.5, "risk_tolerance": 0.3, "target_habits": [], "option_weights": {"mid": 1.0, "low": 1.0, "throw": 1.0, "launcher": 0.8, "backdash": 0.9, "sidestep": 0.9, "wait": 1.0}, "wall_strategy": "none", "note": "Watching your defense after df+1"}),
    2: (0, {"aggression": 0.6, "risk_tolerance": 0.35, "target_habits": [{"situation": "low_defense", "action": "hit", "weight": 0.8}], "option_weights": {"mid": 0.9, "low": 1.5, "throw": 0.8, "launcher": 0.7, "backdash": 0.8, "sidestep": 0.8, "wait": 0.8}, "wall_strategy": "none", "note": "Going low while you stand-block after df+1"}),
    3: (700, {"aggression": 0.6, "risk_tolerance": 0.3, "target_habits": [{"situation": "after_block:df1", "action": "block_high", "weight": 0.5}], "option_weights": {"mid": 1.5, "low": 0.5, "throw": 1.3, "launcher": 0.9, "backdash": 0.8, "sidestep": 0.8, "wait": 0.8}, "wall_strategy": "none", "note": "Switching to mids and throws"}),
}


def session_id(player):
    return f"{STAMP}_{player}_djin_vs_kaz"


class Round:
    def __init__(self, sid, number, frames, rng, health):
        self.sid, self.n, self.frames, self.rng = sid, number, frames, rng
        self.health = dict(health)
        self.moves = {HUMAN: [], BOT: []}
        self.reactions = {HUMAN: [], BOT: []}
        self.crouch = {HUMAN: [], BOT: []}
        self.downed = {HUMAN: [], BOT: []}
        self.thrown = {HUMAN: [], BOT: []}
        self.escaped = {HUMAN: [], BOT: []}
        self.damage = []
        self.events = []
        self.tactical = []
        self.close = []

    def event(self, frame, kind, **fields):
        ev = {"t": "event", "session_id": self.sid, "frame": frame, "round": self.n, "kind": kind}
        ev.update(fields)
        self.events.append(ev)
        return ev

    def attack(self, frame, slot, key, outcome, situation, action=None):
        m = MOVES[key]
        self.moves[slot].append((frame, key))
        contact = frame + m["first"]
        target = 1 - slot
        fields = {"actor": slot, "target": target, "move_id": m["id"], "hit_level": m["level"], "situation": situation}
        if action:
            fields["action"] = action
        if outcome == "block":
            self.event(contact, "block", frame_advantage=m["block"], damage=0, detail={"reaction": 1}, **fields)
            self.reactions[target].append((contact, contact + 16, 1, -m["block"]))
        else:
            self.event(contact, "hit", frame_advantage=m["hit"], damage=m["damage"], detail={"reaction": 12}, **fields)
            self.reactions[target].append((contact, contact + 20, 12, -m["hit"]))
            self.damage.append((contact, target, m["damage"]))
        return contact

    def decision(self, frame, situation, action):
        self.event(frame, "decision_point", actor=HUMAN, situation=situation, action=action)

    def choose(self, frame, chosen, source, probabilities):
        self.tactical.append({"t": "tactical", "session_id": self.sid, "round": self.n, "frame": frame, "frame_asked": frame - 3, "options": sorted(probabilities), "chosen": chosen, "probabilities": probabilities, "source": source})

    def low(self, f, outcome):
        self.close.append((f - 30, f + 90))
        c = self.attack(f, BOT, "kaz_df1", "block", "after_block:df1")
        self.decision(c + 1, "after_block:df1", "block_high" if outcome == "hit" else "block_low")
        self.choose(f + 28, "low", "habit", {"low": 0.7, "mid": 0.2, "throw": 0.1})
        if outcome == "blocked":
            self.crouch[HUMAN].append((c + 4, f + 64))
        c2 = self.attack(f + 30, BOT, "kaz_d4", "hit" if outcome == "hit" else "block", "low_defense", outcome)
        self.decision(c2, "low_defense", outcome)
        if outcome == "blocked":
            self.attack(c2 + 6, HUMAN, "dj_df1", "hit", "punish_window")

    def mid(self, f, outcome):
        self.close.append((f - 30, f + 90))
        c = self.attack(f, BOT, "kaz_df1", "block", "after_block:df1")
        self.decision(c + 1, "after_block:df1", "duck" if outcome == "duck" else "block_high")
        self.choose(f + 28, "mid", "laya", {"low": 0.25, "mid": 0.65, "throw": 0.1})
        if outcome == "duck":
            self.crouch[HUMAN].append((c + 4, f + 70))
            self.attack(f + 30, BOT, "kaz_df2", "hit", "after_block:df1", "duck")
        else:
            c2 = self.attack(f + 30, BOT, "kaz_df2", "block", "after_block:df1", "block_high")
            self.attack(c2 + 6, HUMAN, "dj_df1", "hit", "punish_window")

    def throw(self, f, outcome):
        self.close.append((f - 30, f + 110))
        m = MOVES["kaz_throw"]
        self.moves[BOT].append((f, "kaz_throw"))
        self.choose(f - 3, "throw", "default", {"low": 0.3, "mid": 0.3, "throw": 0.4})
        c = f + m["first"]
        broken = outcome == "broken"
        self.thrown[HUMAN].append((c, c + (12 if broken else 28)))
        if broken:
            self.event(c + 8, "throw_break", actor=HUMAN, target=BOT, move_id=m["id"], hit_level="throw", situation="throw_break", action="break_1", detail={"break": "press_1"})
            self.escaped[HUMAN].append((c + 8, c + 30))
        else:
            self.event(c, "throw", actor=BOT, target=HUMAN, move_id=m["id"], hit_level="throw", damage=m["damage"], situation="throw_break", action="none", detail={"break": "press_1"})
            self.damage.append((c, HUMAN, m["damage"]))
            self.event(c + 28, "knockdown", actor=BOT, target=HUMAN, detail={"cause": "throw"})
            self.downed[HUMAN].append((c + 28, c + 78))
            self.event(c + 78, "wakeup", actor=HUMAN, detail={})
        self.decision(c + 1, "throw_break", "break_1" if broken else "none")

    def jab(self, f, outcome):
        self.close.append((f - 30, f + 50))
        self.attack(f, HUMAN, "dj_jab", "hit", "neutral")

    def build(self, script):
        for f, kind, outcome in script:
            getattr(self, kind)(f, outcome)

    def active(self, spans, frame):
        return next((s for s in spans if s[0] <= frame < s[1]), None)

    def current_move(self, slot, frame):
        for start, key in self.moves[slot]:
            m = MOVES[key]
            if start <= frame < start + m["total"]:
                return m, frame - start + 1
        return None, 0

    def distance(self, frame):
        base = 2600.0 + 300.0 * ((frame // 240) % 2)
        for lo, hi in self.close:
            if lo <= frame < hi:
                return 1300.0
        return base

    def player(self, slot, frame, z):
        m, fim = self.current_move(slot, frame)
        reaction = self.active(self.reactions[slot], frame)
        crouching = self.active(self.crouch[slot], frame) is not None
        downed = self.active(self.downed[slot], frame) is not None
        thrown = self.active(self.thrown[slot], frame) is not None
        name, cid = CHAR[slot]
        hp = self.health[slot]
        if m:
            move_id, total, level, first, last = m["id"], m["total"], m["level"], m["first"], m["last"]
        else:
            move_id, total, level, first, last, fim = (CROUCH if crouching else IDLE), (1 if crouching else 88), "none", 0, 0, (1 if crouching else frame % 88 + 1)
        return {
            "slot": slot, "character_id": cid, "character": name, "health": hp, "recoverable_limit": hp, "max_health": 190,
            "x": 0.0, "y": 1003.5, "z": round(z, 1), "facing": 0 if slot == HUMAN else 32768, "side": slot,
            "move_id": move_id, "frame_in_move": fim, "move_total": total,
            "free_movement": m is None and reaction is None and not downed and not thrown,
            "hit_level": level, "hit_reaction": reaction[2] if reaction else 0,
            "status": 2114 | (DOWNED if downed else 0), "basic_state": 2 if crouching else 1,
            "being_thrown": "press_1" if thrown else "none", "throw_escaped": self.active(self.escaped[slot], frame) is not None,
            "heat_gauge": 0.0, "heat_active": False, "heat_used": False, "rage_active": hp < 40, "power_crush": False,
            "first_active": first, "last_active": last, "first_airborne": 0, "last_airborne": 0,
            "dir_held": "d" if crouching else ("b" if reaction and reaction[2] == 1 else "n"),
            "buttons_held": [], "buttons_pressed": [],
        }

    def situation(self, frame):
        if frame >= self.frames - 30:
            return "round_over", None
        if self.active(self.thrown[HUMAN], frame):
            return "throw", None
        if self.active(self.downed[HUMAN], frame):
            return "knockdown", None
        for slot in (HUMAN, BOT):
            r = self.active(self.reactions[slot], frame)
            if r:
                adv = r[3] if slot == HUMAN else -r[3]
                if adv >= 10:
                    return "punish_window", adv
                return ("pressure" if adv > 0 else "defense" if adv < 0 else "neutral"), adv
        return "neutral", None

    def records(self):
        out = []
        by_frame = {}
        for ev in self.events:
            by_frame.setdefault(ev["frame"], []).append(ev)
        pending = sorted(self.damage)
        out.append({"t": "event", "session_id": self.sid, "frame": 0, "round": self.n, "kind": "round_start", "detail": {"reason": "timer"}})
        plan_frame, plan = PLANS[self.n]
        tactical = {t["frame"]: t for t in self.tactical}
        for frame in range(self.frames):
            while pending and pending[0][0] <= frame:
                _, slot, dmg = pending.pop(0)
                self.health[slot] = max(1, self.health[slot] - dmg)
            d = self.distance(frame) + self.rng.uniform(-40, 40)
            situation, adv = self.situation(frame)
            bucket = next((name for limit, name in BUCKETS if d < limit), "very_far")
            out.append({
                "t": "state", "session_id": self.sid, "frame": frame, "round": self.n, "human_slot": HUMAN,
                "players": [self.player(HUMAN, frame, -d / 2), self.player(BOT, frame, d / 2)],
                "derived": {"distance_mm": round(d, 1), "distance_bucket": bucket, "frame_advantage": adv, "situation": situation, "bearing_deg": 0.0, "timer_s": round(max(0.0, (self.frames - frame) / FPS), 2)},
            })
            for ev in by_frame.get(frame, []):
                out.append(ev)
            if frame == plan_frame:
                out.append({"t": "plan", "session_id": self.sid, "round": self.n, "frame": frame, **plan})
            if frame in tactical:
                out.append(tactical[frame])
        last = self.frames - 1
        winner = HUMAN if self.health[HUMAN] > self.health[BOT] else BOT if self.health[BOT] > self.health[HUMAN] else None
        out.append({"t": "event", "session_id": self.sid, "frame": last, "round": self.n, "kind": "round_end", "detail": {"reason": "timeout", "winner": winner}})
        return out, winner


def summary(sid, number, frames, records, winner, damage_taken):
    learn = LEARNING[number]
    habits = sorted(learn["habits"].items(), key=lambda kv: kv[1]["p"] * kv[1]["n"], reverse=True)
    actions = {"low_defense": "hit", "after_block:df1": "block_high", "throw_break": "none"}
    top = [{"situation": k, "action": actions[k], **v} for k, v in habits if v["n"] >= 2][:3]
    hits = sorted((r for r in records if r["t"] == "event" and r["kind"] in ("hit", "throw") and r.get("target") == HUMAN and r.get("damage")), key=lambda r: (-r["damage"], r["frame"]))
    moments = [{"frame": r["frame"], "kind": r["kind"], "move_id": r["move_id"], "damage": r["damage"], "situation": r["situation"]} for r in hits[:3]]
    prev_fixed = {k for k, v in LEARNING.get(number - 1, {}).get("habits", {}).items() if v["fixed"]}
    fixed = {k for k, v in learn["habits"].items() if v["fixed"]}
    return {
        "t": "round_summary", "session_id": sid, "round": number, "frame": frames - 1, "winner": winner, "human_slot": HUMAN,
        "human_character": "devil_jin", "bot_character": "kazuya", "difficulty": 3,
        "human_damage_taken": damage_taken[HUMAN], "bot_damage_taken": damage_taken[BOT],
        "top_habits": top, "biggest_moments": moments,
        "exploited": [k for k, v in learn["habits"].items() if v["p"] >= 0.6 and v["n"] >= 4 and not v["fixed"]],
        "newly_fixed": sorted(fixed - prev_fixed), "regressed": sorted(prev_fixed - fixed),
    }


def profile(player):
    last = LEARNING[max(LEARNING)]
    return {
        "player": player, "character": "devil_jin", "sessions": 1,
        "habits": {
            "low_defense": {"hit": [7, 1], "blocked": [8, 1], "low_parry": [0, 1]},
            "after_block:df1": {"block_high": [12, 1], "block_low": [7, 1], "duck": [1, 1]},
            "throw_break": {"break_1": [2, 1], "none": [1, 1]},
        },
        "mastery": {k: {"p_learned": v["mastery"], "observations": v["n"], "fixed": v["fixed"], "last_retest": STARTED if v["fixed"] else None} for k, v in last["habits"].items()},
        "bandits": {k: {arm: [round(p * 10), round((1 - p) * 10)] for arm, p in arms.items()} for k, arms in last["bandit"].items()},
        "predictor": None, "history": [],
    }


def dumps(obj):
    return json.dumps(obj, separators=(",", ":"))


def generate(out_dir=None, seed=1, rounds=3, round_seconds=30, player="synth"):
    out = Path(out_dir) if out_dir else data_dir()
    rng = random.Random(seed)
    sid = session_id(player)
    frames = round_seconds * FPS
    for number in range(1, rounds + 1):
        if number not in SCRIPT:
            raise ValueError(f"no script for round {number}; rounds must be 1-{max(SCRIPT)}")
        if max(f for f, _, _ in SCRIPT[number]) + 120 > frames:
            raise ValueError(f"round_seconds {round_seconds} is too short for the round {number} script")
    lines, learning, meta_rounds = [], [], []
    wins = {HUMAN: 0, BOT: 0}
    for number in range(1, rounds + 1):
        r = Round(sid, number, frames, rng, {HUMAN: 190, BOT: 190})
        r.build(SCRIPT[number])
        records, winner = r.records()
        taken = {HUMAN: 190 - r.health[HUMAN], BOT: 190 - r.health[BOT]}
        lines += records
        lines.append(summary(sid, number, frames, records, winner, taken))
        learning.append({"t": "learning_round", "session_id": sid, "round": number, **LEARNING[number]})
        meta_rounds.append({"round": number, "winner": winner, "start_frame": 0, "end_frame": frames - 1})
        if winner is not None:
            wins[winner] += 1
    result = f"{'win' if wins[HUMAN] > wins[BOT] else 'loss' if wins[BOT] > wins[HUMAN] else 'draw'} {wins[HUMAN]}-{wins[BOT]}"
    recording = out / "recordings" / f"{sid}.jsonl"
    try:
        shown = recording.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        shown = recording.as_posix()
    meta = {
        "session_id": sid, "started_at": STARTED, "ended_at": "2026-10-17T13:06:45Z", "game_version": "3.02.02",
        "mode": "synthetic", "stage": "infinite", "player": player, "human_slot": HUMAN,
        "human_character": "devil_jin", "bot_character": "kazuya", "difficulty": 3,
        "rounds": meta_rounds, "result": result, "recording": shown,
    }
    validate(lines, learning, meta, profile(player))
    for sub in ("recordings", "sessions", "learning", "profiles"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    recording.write_text("".join(dumps(l) + "\n" for l in lines), encoding="utf-8")
    (out / "sessions" / f"{sid}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (out / "learning" / f"{sid}.jsonl").write_text("".join(dumps(l) + "\n" for l in learning), encoding="utf-8")
    (out / "profiles" / f"{player}_devil_jin.json").write_text(json.dumps(profile(player), indent=2), encoding="utf-8")
    return sid


def validate(lines, learning, meta, prof):
    names = {"state": "gamestate", "event": "event", "round_summary": "round_summary"}
    errors = []
    for i, line in enumerate(lines):
        if line["t"] in names:
            errors += [f"line {i + 1} ({line['t']}): {e}" for e in check(names[line["t"]], line)]
        elif line["t"] == "plan":
            body = {k: v for k, v in line.items() if k not in ("t", "session_id", "round", "frame")}
            errors += [f"line {i + 1} (plan): {e}" for e in check("gameplan", body)]
    for l in learning:
        errors += [f"learning round {l['round']}: {e}" for e in check("metrics", l, "round")]
    errors += [f"session: {e}" for e in check("session", meta)]
    errors += [f"profile: {e}" for e in check("profile", prof)]
    if errors:
        raise ValueError("synthetic session breaks the contracts:\n" + "\n".join(errors[:20]))


def ensure(out_dir=None, player="synth"):
    out = Path(out_dir) if out_dir else data_dir()
    sid = session_id(player)
    if (out / "recordings" / f"{sid}.jsonl").exists() and (out / "sessions" / f"{sid}.json").exists():
        return sid
    return generate(out, player=player)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate the synthetic Kumite session: habit detected, exploited, then fixed")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--round-seconds", type=int, default=30)
    ap.add_argument("--player", default="synth")
    ap.add_argument("--out", help="data directory (default: DATA_DIR or ./data)")
    a = ap.parse_args(argv)
    sid = generate(a.out, a.seed, a.rounds, a.round_seconds, a.player)
    out = Path(a.out) if a.out else data_dir()
    print(f"wrote {sid}")
    for sub, ext in (("recordings", "jsonl"), ("sessions", "json"), ("learning", "jsonl")):
        print(f"  {out / sub / f'{sid}.{ext}'}")
    print(f"  {out / 'profiles' / f'{a.player}_devil_jin.json'}")


if __name__ == "__main__":
    main()
