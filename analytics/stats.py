import bisect
from collections import defaultdict

PUNISHABLE = -10
PUNISH_WINDOW = 10
CONNECT = ("hit", "counter_hit")
DAMAGING = CONNECT + ("throw",)
LOWS = ("low", "special_low")
TIMELINE_STEP = 30


def rate(num, den):
    return round(min(num / den, 1.0), 3) if den else None


def rounds_of(records):
    found = sorted({r["round"] for r in records if isinstance(r.get("round"), int)})
    return found or [1]


class Situations:
    def __init__(self, records):
        self.by_round = defaultdict(list)
        for r in records:
            if r.get("t") == "state" and isinstance(r.get("frame"), int):
                situation = (r.get("derived") or {}).get("situation")
                if situation:
                    self.by_round[r.get("round")].append((r["frame"], situation))
        self.frames = {}
        for k, v in self.by_round.items():
            v.sort(key=lambda x: x[0])
            self.frames[k] = [f for f, _ in v]

    def at(self, round_, frame):
        frames = self.frames.get(round_)
        if not frames:
            return None
        i = bisect.bisect_right(frames, frame) - 1
        return self.by_round[round_][i][1] if i >= 0 else None


def winners(records, meta):
    found = {}
    for e in records:
        if e.get("t") == "event" and e.get("kind") == "round_end":
            found[e.get("round")] = (e.get("detail") or {}).get("winner")
    for r in meta.get("rounds") or []:
        if isinstance(r, dict) and found.get(r.get("round")) is None:
            found[r.get("round")] = r.get("winner")
    return found


def block(evs, human, situations, won):
    bot = 1 - human
    by_situation = defaultdict(int)
    for e in evs:
        if e["kind"] in DAMAGING and e.get("target") == human and (e.get("damage") or 0) > 0:
            key = e.get("situation") or situations.at(e.get("round"), e.get("frame", 0)) or "neutral"
            by_situation[key] += e["damage"]
    opps = [e for e in evs if e["kind"] == "block" and e.get("actor") == bot and e.get("target") == human and isinstance(e.get("frame_advantage"), int) and e["frame_advantage"] <= PUNISHABLE]
    hits_by_human = [e for e in evs if e["kind"] in CONNECT and e.get("actor") == human]
    punished = sum(1 for o in opps if any(h.get("round") == o.get("round") and 0 < h["frame"] - o["frame"] <= abs(o["frame_advantage"]) + PUNISH_WINDOW for h in hits_by_human))
    throws = sum(1 for e in evs if e["kind"] == "throw" and e.get("actor") == bot and e.get("target") == human)
    breaks = [e for e in evs if e["kind"] == "throw_break" and e.get("actor") == human]
    by_type = defaultdict(int)
    for e in breaks:
        d = e.get("detail") or {}
        by_type[d.get("input") or d.get("break") or "unknown"] += 1
    lows = [e for e in evs if e.get("actor") == bot and e.get("target") == human and e.get("hit_level") in LOWS and e["kind"] in ("block",) + CONNECT]
    adv = [-e["frame_advantage"] for e in evs if e["kind"] == "block" and e.get("target") == human and isinstance(e.get("frame_advantage"), int)]
    return {
        "damage_taken_by_situation": dict(by_situation),
        "punish_rate": rate(punished, len(opps)),
        "throw_break_rate": rate(len(breaks), throws),
        "low_block_rate": rate(sum(1 for e in lows if e["kind"] == "block"), len(lows)),
        "counter_hits_taken": sum(1 for e in evs if e["kind"] == "counter_hit" and e.get("target") == human),
        "counter_hits_given": sum(1 for e in evs if e["kind"] == "counter_hit" and e.get("actor") == human),
        "avg_adv_after_block": round(sum(adv) / len(adv), 2) if adv else None,
        "rounds_won": won,
        "throw_breaks_by_type": dict(by_type),
    }


def health_timeline(records, human):
    out = defaultdict(list)
    last = {}
    for r in records:
        if r.get("t") != "state" or not isinstance(r.get("players"), list) or len(r["players"]) != 2:
            continue
        rnd, frame = r.get("round"), r.get("frame", 0)
        point = [frame, r["players"][human].get("health"), r["players"][1 - human].get("health")]
        if frame % TIMELINE_STEP == 0:
            out[rnd].append(point)
        last[rnd] = point
    for rnd, point in last.items():
        if not out[rnd] or out[rnd][-1][0] != point[0]:
            out[rnd].append(point)
    return {str(k): v for k, v in sorted(out.items(), key=lambda kv: (kv[0] is None, kv[0]))}


def compute(session_id, meta, records):
    human = meta.get("human_slot", 0) if meta.get("human_slot") in (0, 1) else 0
    evs = [r for r in records if r.get("t") == "event" and isinstance(r.get("kind"), str) and isinstance(r.get("frame"), int)]
    situations = Situations(records)
    won = winners(records, meta)

    def won_flag(rnd):
        w = won.get(rnd)
        return None if w is None else int(w == human)

    per_round = [{"round": rnd, **block([e for e in evs if e.get("round") == rnd], human, situations, won_flag(rnd))} for rnd in rounds_of(records)]
    total_won = sum(1 for w in won.values() if w is not None and w == human) if any(w is not None for w in won.values()) else None
    return {
        "session_id": session_id,
        "rounds": per_round,
        "totals": block(evs, human, situations, total_won),
        "health_timeline": health_timeline(records, human),
    }
