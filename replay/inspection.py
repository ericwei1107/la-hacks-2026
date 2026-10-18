import html
import json
import re
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path

from replay.reader import Recording

MOMENT_KINDS = {"hit", "counter_hit", "block", "whiff", "throw", "throw_break",
                "knockdown", "decision_point"}


class RoundContext:
    def __init__(self, states, events):
        self.states = sorted(states, key=lambda record: (record.data["frame"], record.line))
        self.keys = [(record.data["frame"], record.line) for record in self.states]
        ends = [record.data["frame"] for record in events if record.data["kind"] == "round_end"]
        self.end = min(ends) if ends else None

    def before(self, event):
        position = bisect_right(self.keys, (event.data["frame"], event.line)) - 1
        return self.states[position] if position >= 0 else None

    def outcome(self, event, state):
        start = event.data["frame"]
        requested_end = start + 60
        end = min(requested_end, self.end) if self.end is not None else requested_end
        left = bisect_right(self.keys, (start - 1, float("inf")))
        right = bisect_right(self.keys, (end, float("inf")))
        samples = self.states[left:right] if end >= start else []
        if samples:
            end = min(end, samples[-1].data["frame"])
        frames = [record.data["frame"] for record in samples]
        complete = bool(samples) and frames == list(range(start, end + 1))
        expected_end = min(requested_end, self.end) if self.end is not None else requested_end
        if not samples or samples[-1].data["frame"] < expected_end:
            complete = False
        identity = state.data["human_slot"] if state else None
        stable = identity is not None and all(record.data["human_slot"] == identity for record in samples)
        increases = False
        losses = {0: 0, 1: 0}
        for previous, current in zip(samples, samples[1:]):
            previous_hp = {p["slot"]: p["health"] for p in previous.data["players"]}
            for player in current.data["players"]:
                change = previous_hp[player["slot"]] - player["health"]
                increases |= change < 0
                losses[player["slot"]] += max(0, change)
        reliable = complete and stable and not increases and state is not None and state.data["frame"] == start
        return {
            "start_frame": start, "end_frame": max(start, end), "requested_end_frame": requested_end,
            "window_complete": complete and end == requested_end,
            "coverage_complete": complete,
            "human_identity_consistent": stable,
            "health_increase_observed": increases,
            "human_health_loss": losses[identity] if reliable else None,
            "bot_health_loss": losses[1 - identity] if reliable else None,
            "state_evidence": {
                "first": {"line": samples[0].line, "frame": samples[0].data["frame"]} if samples else None,
                "last": {"line": samples[-1].line, "frame": samples[-1].data["frame"]} if samples else None,
            },
            "note": "Observed health loss in this window is not damage caused by or avoidable at this moment. Overlapping windows must not be summed.",
        }


def moment_kind(event, human):
    kind, actor, target = event["kind"], event.get("actor"), event.get("target")
    if human is None:
        return "unattributed_event"
    if kind == "decision_point":
        return "human_decision" if actor == human else ("unattributed_event" if actor is None else None)
    if kind in {"hit", "counter_hit"}:
        return "human_hit" if target == human else ("human_landed_hit" if actor == human else "unattributed_event")
    if kind == "block":
        return "human_attack_blocked" if actor == human else ("human_block" if target == human else "unattributed_event")
    if kind == "whiff":
        return "human_whiff" if actor == human else ("opponent_whiff" if actor is not None else "unattributed_event")
    if kind == "throw":
        return "human_thrown" if target == human else ("human_throw_attempt" if actor == human else "unattributed_event")
    if kind == "throw_break":
        return "human_throw_break" if actor == human else ("opponent_throw_break" if target == human else "unattributed_event")
    return "human_knockdown" if target == human else ("opponent_knockdown" if actor == human else "unattributed_event")


DESCRIPTIONS = {
    "human_hit": "The recording reports that the human was hit.",
    "human_landed_hit": "The recording reports that the human landed a hit.",
    "human_attack_blocked": "The opponent blocked the human's attack.",
    "human_block": "The human blocked the opponent's attack; a punish is not established.",
    "human_whiff": "The recording labels the human's attack as a whiff.",
    "opponent_whiff": "The recording labels the opponent's attack as a whiff; punish range and timing are not established.",
    "human_thrown": "The recording reports a throw against the human; a missed break is not established.",
    "human_throw_attempt": "The human attempted a throw; this event alone does not establish that it landed.",
    "human_throw_break": "The recording reports that the human broke a throw.",
    "opponent_throw_break": "The recording reports that the opponent broke the human's throw.",
    "human_knockdown": "The recording reports that the human was knocked down.",
    "opponent_knockdown": "The recording reports that the opponent was knocked down.",
    "human_decision": "The recorder explicitly labeled a human decision.",
    "unattributed_event": "A relevant event was recorded, but its human role cannot be established.",
}


def build_inspection(recording: Recording) -> dict:
    states, events = defaultdict(list), defaultdict(list)
    tactical_sources = Counter()
    for record in recording.records:
        data = record.data
        if data["t"] == "state":
            states[data["round"]].append(record)
        elif data["t"] == "event":
            events[data["round"]].append(record)
        elif data["t"] == "tactical":
            source = data.get("source")
            tactical_sources[source if isinstance(source, str) else "unknown"] += 1
    contexts = {round_number: RoundContext(states[round_number], events[round_number])
                for round_number in sorted(set(states) | set(events))}
    moments = []
    for round_number, context in contexts.items():
        for record in sorted(events[round_number], key=lambda row: (row.data["frame"], row.line)):
            event = record.data
            if event["kind"] not in MOMENT_KINDS:
                continue
            state = context.before(record)
            human = state.data["human_slot"] if state else None
            kind = moment_kind(event, human)
            if kind is None:
                continue
            missing = []
            snapshot = None
            if state:
                players = {player["slot"]: player for player in state.data["players"]}
                snapshot = {
                    "state_frame": state.data["frame"], "line": state.line,
                    "age_frames": event["frame"] - state.data["frame"],
                    "human": {key: players[human].get(key) for key in
                              ("slot", "character", "health", "move_id", "dir_held", "buttons_pressed", "free_movement")},
                    "opponent": {key: players[1 - human].get(key) for key in
                                 ("slot", "character", "health", "move_id", "free_movement")},
                    "distance_mm": state.data["derived"].get("distance_mm"),
                    "distance_bucket": state.data["derived"].get("distance_bucket"),
                    "recorded_situation": state.data["derived"].get("situation"),
                }
                if snapshot["age_frames"]:
                    missing.append(f"State context is {snapshot['age_frames']} frame(s) older than the event")
            else:
                missing.extend(["No prior state in this round", "Human identity is unknown at this event"])
            if event.get("actor") is None:
                missing.append("Event actor is missing")
            action = event.get("action") if kind == "human_decision" else None
            if not action:
                missing.append("No explicit human action label; recorded inputs or bot choices are not intent labels")
            if not event.get("situation"):
                missing.append("No explicit situation label on the event")
            if "damage" not in event:
                missing.append("Event damage was not recorded")
            missing.append("Move names, legal alternatives, punish timing, and best-option scoring are not evaluated")
            outcome = context.outcome(record, state)
            if not outcome["coverage_complete"]:
                missing.append("Outcome frame coverage is missing, duplicated, or incomplete")
            if not outcome["window_complete"]:
                missing.append("The full following 60-frame window is not available")
            if outcome["health_increase_observed"]:
                missing.append("Health increased in the window; recovery or reset prevents a damage-total claim")
            if state and not outcome["human_identity_consistent"]:
                missing.append("Human slot changes in the outcome window; damage cannot be attributed reliably")
            moments.append({
                "round": round_number, "frame": event["frame"],
                "round_counter_seconds": round(event["frame"] / 60, 3),
                "kind": kind, "event_kind": event["kind"], "description": DESCRIPTIONS[kind],
                "human_slot": human, "actor": event.get("actor"), "target": event.get("target"),
                "move_id": event.get("move_id"), "hit_level": event.get("hit_level"),
                "recorded_frame_advantage": event.get("frame_advantage"),
                "frame_advantage_perspective": "Unverified recorder value; not converted into a human punish recommendation",
                "situation": event.get("situation"), "human_action": action,
                "event_damage": event.get("damage"), "context": snapshot, "outcome": outcome,
                "evidence": [{"line": record.line, "type": "event", "round": round_number,
                              "frame": event["frame"], "record": event}],
                "missing_information": missing,
            })
    limitations = [
        "Observation-only inspection, separate from the contract report and Jev scoring. No event is automatically a mistake.",
        "Round counter seconds are not video or wall-clock timestamps.",
        "Health-loss windows may overlap and must not be summed or treated as causal or avoidable damage.",
        "Recorded inputs do not establish player intent. Bot tactical records never supply human actions.",
    ]
    if not any(moment["kind"] == "human_decision" for moment in moments):
        limitations.append("No explicit human decision-point labels are available")
    if not recording.counts["round_summary"]:
        limitations.append("No round_summary records are available")
    return {
        "format": "kumite.inspection.v1", "session_id": recording.session_id,
        "source": str(recording.path), "record_counts": dict(recording.counts),
        "tactical_sources": dict(tactical_sources), "reader_warnings": recording.warnings,
        "limitations": limitations,
        "rounds": [{"round": number, "state_count": len(context.states),
                    "first_frame": context.states[0].data["frame"] if context.states else None,
                    "last_frame": context.states[-1].data["frame"] if context.states else None,
                    "recorded_end_frame": context.end}
                   for number, context in contexts.items()],
        "moment_counts": dict(Counter(moment["kind"] for moment in moments)),
        "moments": moments,
    }


def escape(value) -> str:
    text = html.escape(str(value), quote=False).replace("\n", " ").replace("\r", " ")
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", text)


def render_markdown(report: dict) -> str:
    lines = ["# Recording inspection", "", f"Session: {escape(report['session_id'])}",
             f"Source: {escape(report['source'])}", "", "## Coverage", ""]
    for kind, count in report["record_counts"].items():
        lines.append(f"- {escape(kind)}: {count}")
    lines.extend(["", "Bot tactical sources:", ""])
    lines.extend(f"- {escape(source)}: {count}" for source, count in report["tactical_sources"].items())
    lines.extend(["", "Observed moment counts:", ""])
    lines.extend(f"- {escape(kind)}: {count}" for kind, count in report["moment_counts"].items())
    lines.extend(["", "## Limitations", ""])
    for note in report["limitations"] + report["reader_warnings"]:
        lines.append(f"- {escape(note)}")
    lines.extend(["", "## Observed moments", ""])
    for moment in report["moments"]:
        lines.extend([
            f"### Round {moment['round']}, frame {moment['frame']}: {escape(moment['kind'])}", "",
            escape(moment["description"]), "",
            f"Evidence: JSONL line {moment['evidence'][0]['line']}; actor={moment['actor']}, target={moment['target']}, human={moment['human_slot']}.",
            f"Recorded move ID: {moment['move_id']}; event damage: {moment['event_damage'] if moment['event_damage'] is not None else 'unknown'}.",
            f"Human action: {escape(moment['human_action']) if moment['human_action'] else 'unknown'}. Situation label: {escape(moment['situation']) if moment['situation'] else 'unknown'}.",
        ])
        outcome = moment["outcome"]
        boundary = outcome["state_evidence"]
        lines.extend([
            f"Observed health loss in frames {outcome['start_frame']}–{outcome['end_frame']}: human={outcome['human_health_loss'] if outcome['human_health_loss'] is not None else 'unknown'}, bot={outcome['bot_health_loss'] if outcome['bot_health_loss'] is not None else 'unknown'}.",
            f"Coverage complete: {outcome['coverage_complete']}. Full 60-frame window: {outcome['window_complete']}.", "",
            f"Health-window state lines: {boundary['first']['line'] if boundary['first'] else 'unknown'} to {boundary['last']['line'] if boundary['last'] else 'unknown'}.", "",
            "Missing information:", "",
        ])
        lines.extend(f"- {escape(note)}" for note in moment["missing_information"])
        lines.append("")
    return "\n".join(lines) + "\n"


def write_inspection(report: dict, output_dir: str | Path, overwrite: bool = False):
    output_dir = Path(output_dir)
    slug = re.sub(r"[^A-Za-z0-9_.-]", "_", report["session_id"]).strip("._-")[:120] or "session"
    json_path = output_dir / f"{slug}.inspection.json"
    markdown_path = output_dir / f"{slug}.inspection.md"
    for path in (json_path, markdown_path):
        if path.resolve() == Path(report["source"]).resolve():
            raise ValueError("Output cannot overwrite the recording")
        if path.exists() and not overwrite:
            raise FileExistsError(f"Report already exists: {path}; use --overwrite to regenerate")
    payload = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    markdown = render_markdown(report)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(payload, encoding="utf-8")
    markdown_path.write_text(markdown, encoding="utf-8")
    return json_path, markdown_path
