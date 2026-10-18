from datetime import datetime, timezone
from store import data_dir
from analytics import stats as analytics_stats
from analytics.metrics import learning_metrics
from analytics.repository import DataError, FileRepository, normalized_learning

CONNECT = ("hit", "counter_hit")
DAMAGING = CONNECT + ("throw",)
OPTIONS = [("block_low", "d/b", 0.55), ("press", "1", 0.25), ("sidestep", "u", 0.20)]


def human(session):
    return session.meta.get("human_slot", 0)


def events(session, round_=None):
    return [e for e in session.of("event") if round_ is None or e["round"] == round_]


def rounds(session):
    found = sorted({r["round"] for r in session.stream()})
    return found or [1]


def winner(session, round_):
    return analytics_stats.winners(session.records, session.meta).get(round_)


def damage_to(evs, slot):
    return sum(e.get("damage", 0) for e in evs if e["kind"] in DAMAGING and e.get("target") == slot)


def round_summary(session, round_):
    for s in session.of("round_summary"):
        if s["round"] == round_:
            return s
    h = human(session)
    evs = events(session, round_)
    hits = sorted((e for e in evs if e["kind"] in CONNECT + ("throw",)), key=lambda e: e.get("damage", 0), reverse=True)
    moments = []
    for e in hits[:3]:
        m = {"frame": e["frame"], "kind": e["kind"]}
        for k in ("move_id", "damage", "situation"):
            if k in e:
                m[k] = e[k]
        moments.append(m)
    end = max((r["frame"] for r in session.stream() if r.get("round") == round_ and "frame" in r), default=0)
    return {
        "t": "round_summary",
        "session_id": session.id,
        "round": round_,
        "frame": end,
        "winner": winner(session, round_),
        "human_slot": h,
        "human_character": session.meta.get("human_character", "unknown"),
        "bot_character": session.meta.get("bot_character", "unknown"),
        "difficulty": session.meta.get("difficulty", 1),
        "human_damage_taken": damage_to(evs, h),
        "bot_damage_taken": damage_to(evs, 1 - h),
        "top_habits": [],
        "biggest_moments": moments,
        "exploited": [],
        "newly_fixed": [],
        "regressed": [],
    }


def stats(session):
    return analytics_stats.compute(session.id, session.meta, session.records)


def learning(session):
    try:
        lines = normalized_learning(session.id, session.load_learning(), str(session.path))
    except ValueError as exc:
        raise DataError(f'{session.id}: invalid learning data') from exc
    return learning_metrics(session.id, lines, finetune(session.id))


def finetune(sid):
    return FileRepository(data_dir())._evaluation(sid)[1]


def coach_text(summary):
    if summary.get("newly_fixed"):
        habit = summary["newly_fixed"][0].replace("_", " ")[:40]
        return f"You've fixed your {habit}. Nice work. I'll test it again later, so keep it up.", "praise"
    if summary.get("top_habits"):
        top = summary["top_habits"][0]
        situation = top["situation"].replace("_", " ")
        return f"Mock coach: in {situation[:40]} you repeated an option. Try a different answer next round.", "warn"
    taken = summary.get("human_damage_taken", 0)
    return f"Round {summary['round']}: you took {taken} damage. Watch what I do after my moves get blocked.", "info"


def report(session):
    h = human(session)
    summaries = [round_summary(session, r) for r in rounds(session)]
    habits = []
    last = summaries[-1] if summaries else {}
    for t in last.get("top_habits", []):
        moments = [m["frame"] for s in summaries for m in s.get("biggest_moments", []) if m.get("situation") == t["situation"]]
        entry = {"situation": t["situation"], "action": t["action"], "count": t["n"], "p": t["p"], "min_change": f"Change your answer in {t['situation'].replace('_', ' ')}", "moments": moments}
        if "mastery" in t:
            entry["mastery"] = t["mastery"]
        habits.append(entry)
    points = []
    for e in events(session):
        if e.get("target") != h or e["kind"] not in ("block", "throw") + CONNECT:
            continue
        actual = "blocked" if e["kind"] == "block" else "got_hit"
        points.append({
            "frame": e["frame"],
            "round": e["round"],
            "situation": e.get("situation") or f"{e['kind']} by move {e.get('move_id', '?')}",
            "actual": actual,
            "best": OPTIONS[0][0],
            "options": [{"name": n, "command": c, "p": p} for n, c, p in OPTIONS],
            "why": "Mock analysis: the replay service will score real options with Jev.",
            "cost": e.get("damage", 0),
            "good": e["kind"] == "block",
        })
    won = sum(1 for s in summaries if s["winner"] == h)
    lost = sum(1 for s in summaries if s["winner"] is not None and s["winner"] != h)
    result = session.meta.get("result") or (f"{'win' if won > lost else 'loss' if lost > won else 'draw'} {won}-{lost}" if won or lost else "")
    return {
        "session_id": session.id,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "result": result,
        "habits": habits,
        "decision_points": sorted(points, key=lambda p: p["cost"], reverse=True)[:10],
        "went_well": [f"Blocked {sum(1 for p in points if p['good'])} attacks"],
        "drills": ["Practice: record the dummy doing df+1 into a low or a mid, and block on reaction"],
    }


def profile(session, player):
    character = session.meta.get("human_character", "unknown")
    habits, mastery, bandits = {}, {}, {}
    if session.learning:
        last = sorted(session.learning, key=lambda l: l["round"])[-1]
        for habit, v in last.get("habits", {}).items():
            n = v.get("n", 0)
            hit = round(v.get("p", 0) * n)
            habits[habit] = {"hit": [hit, 1], "other": [n - hit, 1]}
            if "mastery" in v:
                mastery[habit] = {"p_learned": v["mastery"], "observations": n, "fixed": bool(v.get("fixed")), "last_retest": None}
        for key, arms in last.get("bandit", {}).items():
            bandits[key] = {arm: [round(p * 10), round((1 - p) * 10)] for arm, p in arms.items()}
    return {"player": player, "character": character, "sessions": 1, "habits": habits, "mastery": mastery, "bandits": bandits, "predictor": None, "history": []}
