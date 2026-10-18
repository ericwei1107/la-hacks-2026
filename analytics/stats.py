import bisect
from collections import defaultdict

from analytics.observability import traced

CALCULATION_VERSION = 4
PUNISHABLE = -10
PUNISH_WINDOW = 10
CONNECT = ("hit", "counter_hit")
DAMAGING = CONNECT + ("throw",)
LOWS = ("low",)
TIMELINE_STEP = 30


def rate(num, den):
    return round(num / den, 3) if den and num <= den else None


def rounds_of(records):
    found = sorted({r["round"] for r in records if r.get('t') in ('state', 'event', 'round_summary') and type(r.get("round")) is int})
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
    found = {r['round']: r.get('winner') for r in meta.get('rounds', [])}
    for e in records:
        if e.get('t') == 'round_summary':
            winner = e.get('winner')
        elif e.get('t') == 'event' and e.get('kind') == 'round_end':
            winner = (e.get('detail') or {}).get('winner')
        else:
            continue
        if winner is not None:
            found[e['round']] = winner
    if any(w is not None and (type(w) is not int or w not in (0, 1)) for w in found.values()):
        from analytics.repository import DataError
        raise DataError('Invalid round winner in session metadata or recording')
    return found


def opportunities(evs, human):
    bot = 1 - human
    opps = [e for e in evs if e["kind"] == "block" and e.get("actor") == bot and e.get("target") == human and isinstance(e.get("frame_advantage"), int) and e["frame_advantage"] <= PUNISHABLE]
    hits_by_human = [e for e in evs if e['kind'] in CONNECT and e.get('actor') == human and e.get('target') == bot]
    matched = {}
    for hit in sorted(hits_by_human, key=lambda h: (h['round'], h['frame'])):
        candidates = [i for i, o in enumerate(opps) if i not in matched and o['round'] == hit['round'] and 0 < hit['frame'] - o['frame'] <= abs(o['frame_advantage']) + PUNISH_WINDOW]
        if candidates:
            matched[max(candidates, key=lambda i: (opps[i]['frame'], i))] = hit
    throws = [e for e in evs if e["kind"] == "throw" and e.get("actor") == bot and e.get("target") == human]
    breaks = [e for e in evs if e["kind"] == "throw_break" and e.get("actor") == human]
    lows = [e for e in evs if e.get("actor") == bot and e.get("target") == human and e.get("hit_level") in LOWS and e["kind"] in ("block",) + CONNECT]
    return {'low_defense': lows, 'throw_defense': throws, 'breaks': breaks, 'punish_conversion': opps, 'punish_matches': matched}


def block(evs, human, situations, won):
    counted = opportunities(evs, human)
    by_situation = defaultdict(int)
    for e in evs:
        if e["kind"] in DAMAGING and e.get("target") == human and (e.get("damage") or 0) > 0:
            key = e.get("situation") or situations.at(e.get("round"), e.get("frame", 0)) or "neutral"
            by_situation[key] += e["damage"]
    by_type = defaultdict(int)
    for e in counted['breaks']:
        d = e.get("detail") or {}
        by_type[d.get("input") or d.get("break") or "unknown"] += 1
    lows = counted['low_defense']
    adv = [-e["frame_advantage"] for e in evs if e["kind"] == "block" and e.get("target") == human and isinstance(e.get("frame_advantage"), int)]
    return {
        "damage_taken_by_situation": dict(by_situation),
        "punish_rate": rate(len(counted['punish_matches']), len(counted['punish_conversion'])),
        "throw_break_rate": rate(len(counted['breaks']), len(counted['throw_defense'])),
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


@traced('stats.reduce')
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
