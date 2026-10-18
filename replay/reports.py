import asyncio
import importlib
import json
import os
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from replay.config import ROOT
from replay.inspection import build_inspection
from replay.reader import read_recording
from replay.scoring import JevScorer

REPORT_SCHEMA = json.loads((ROOT / "contracts/report.schema.json").read_text())
REPORT_VALIDATOR = Draft202012Validator(REPORT_SCHEMA)
SESSION_VALIDATOR = Draft202012Validator(json.loads((ROOT / "contracts/session.schema.json").read_text()))


def checked_id(session_id):
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,179}", session_id)
            or session_id.split("_")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}):
        raise ValueError("Invalid session ID: use letters, digits, hyphens and underscores")
    return session_id


def within(root, path):
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("Data path escapes DATA_DIR")
    return resolved


def default_options(character, moment):
    module = importlib.import_module("replay.options")
    return module.generate_options(character, moment)


def candidate_options(generator, moment):
    if not moment.get("context") or moment["context"]["age_frames"] != 0:
        return [], [], "An exact-frame human state is unavailable"
    if not moment.get("human_action") or not moment.get("situation"):
        return [], [], "The recorder did not supply both situation and human action"
    try:
        generated = generator(moment["context"]["human"]["character"], moment)
        options, limitations = generated["options"], generated["limitations"]
        valid = (isinstance(options, list) and 2 <= len(options) <= 255
                 and isinstance(limitations, list) and all(isinstance(item, str) for item in limitations)
                 and all(isinstance(option, dict) and all(isinstance(option.get(key), str) and option[key].strip()
                         for key in ("id", "name", "command", "description")) for option in options))
        if not valid or len({option["id"] for option in options}) != len(options):
            return [], limitations if isinstance(limitations, list) else [], "Option generator supplied no valid comparison menu"
        return [{key: option[key] for key in ("id", "name", "command", "description")} for option in options], limitations, None
    except Exception:
        return [], [], "Character option generator is unavailable or could not resolve this decision"


class ReportService:
    def __init__(self, data_dir, scorer=None, option_generator=None):
        self.data_dir = Path(data_dir).resolve()
        self.scorer = scorer or JevScorer.from_env()
        self.option_generator = option_generator or default_options

    def locate(self, session_id):
        checked_id(session_id)
        canonical = within(self.data_dir, self.data_dir / "recordings" / f"{session_id}.jsonl")
        if canonical.is_file():
            return canonical
        samples = within(self.data_dir, self.data_dir / "samples")
        matches = []
        for path in sorted(samples.rglob("*.jsonl")):
            within(self.data_dir, path)
            try:
                with path.open(encoding="utf-8-sig") as source:
                    first = next((line for line in source if line.strip()), "{}")
                if json.loads(first).get("session_id") == session_id:
                    matches.append(path)
            except (ValueError, AttributeError):
                continue
        if len(matches) > 1:
            raise ValueError("Several sample recordings match this session; install one canonical recordings/<session_id>.jsonl")
        if not matches:
            raise FileNotFoundError("No extracted recording found for this session")
        return matches[0]

    def metadata(self, session_id, recording_path, limitations):
        candidates = [self.data_dir / "sessions" / f"{session_id}.json",
                      recording_path.with_suffix(".session.json")]
        for candidate in candidates:
            candidate = within(self.data_dir, candidate)
            if not candidate.is_file():
                continue
            try:
                metadata = json.loads(candidate.read_text(encoding="utf-8-sig"))
                SESSION_VALIDATOR.validate(metadata)
                if metadata["session_id"] != session_id:
                    raise ValueError("Session metadata ID mismatch")
                return metadata
            except (ValueError, ValidationError):
                limitations.append("Session metadata is invalid or mismatched; result is unknown")
                return {}
        limitations.append("Session metadata is missing; result is unknown")
        return {}

    async def analyze(self, session_id):
        path = await asyncio.to_thread(self.locate, session_id)
        recording = await asyncio.to_thread(read_recording, path)
        if recording.session_id != session_id:
            raise ValueError("Recording session ID does not match requested session")
        inspection = await asyncio.to_thread(build_inspection, recording)
        limitations = list(recording.warnings)
        if not recording.counts["round_summary"]:
            limitations.append("No round_summary records are available")
        limitations.extend([
            "Learning/mastery data is not evaluated in this report; no improvement claim is inferred.",
            "Only explicit human decision-point events are scored. Observed hits, inputs and bot tactical choices are not inferred human intent.",
            "Jev probabilities are model preference estimates among supplied candidates, not success or win probabilities or proof of optimality.",
            "Snapshots at labeled decisions may already reflect the action's outcome; a pre-action state is not established.",
            "Round/frame references are game counters, not clip timestamps. Observed health loss is not avoidable damage; cost is omitted.",
        ])
        metadata = await asyncio.to_thread(self.metadata, session_id, path, limitations)
        synthetic = "synthetic" in path.parts or metadata.get("mode") == "synthetic"
        if synthetic:
            limitations.append("SYNTHETIC sample: these observations are not evidence of a real player's performance")
        points, items = [], []
        for moment in inspection["moments"]:
            if moment["kind"] != "human_decision":
                continue
            index = len(points)
            options, option_limits, reason = candidate_options(self.option_generator, moment)
            point = {
                "round": moment["round"], "frame": moment["frame"],
                "situation": moment["situation"] or "unknown", "actual": moment["human_action"] or "unknown",
                "recorded_action": moment["human_action"], "best": "unavailable", "options": [],
                "candidates": options, "limitations": option_limits,
                "missing_information": [value for value in moment["missing_information"]
                                        if not value.startswith("Move names, legal alternatives")],
                "evidence": moment["evidence"], "context": moment["context"],
                "observed_outcome": moment["outcome"],
                "scoring": {"status": "unavailable", "reason": reason or "Jev scoring is unavailable"},
                "why": reason or "Jev scoring is unavailable; no best response is asserted",
            }
            if options:
                items.append((f"d{index}", moment, options))
            points.append(point)
        scores, failure = await self.scorer.score(items) if items else ({}, "No scoreable option menus are available")
        for identifier, _, options in items:
            point = points[int(identifier[1:])]
            answer = scores.get(identifier)
            if answer is None:
                point["scoring"]["reason"] = failure
                point["why"] = failure
                continue
            point["options"] = [{"name": option["name"], "command": option["command"],
                                  "p": answer["probabilities"][option["id"]]} for option in options]
            chosen = next(option for option in options if option["id"] == answer["choice"])
            point["best"] = chosen["name"]
            point["scoring"] = {"status": "scored", "provider": "Jev", "model": answer["model"],
                                "meaning": "Preference among supplied candidates", "choice_id": answer["choice"]}
            if answer.get("confidence") is not None:
                point["scoring"]["confidence"] = answer["confidence"]
            point["why"] = (f"Jev preferred {chosen['name']} among the supplied candidates. "
                            f"Candidate description: {chosen['description']} "
                            "Timing, outcome and counterfactual damage are not established.")
        counts = Counter((point["situation"], point["actual"]) for point in points
                         if point["situation"] != "unknown" and point["recorded_action"] is not None)
        totals = Counter(point["situation"] for point in points if point["recorded_action"] is not None)
        habits = [{"situation": situation, "action": action, "count": count,
                   "p": count / totals[situation], "p_source": "observed action frequency within this situation",
                   "min_change": "Review these recorded decisions; a change that would flip an exchange is not established.",
                   "moments": [point["frame"] for point in points if (point["situation"], point["actual"]) == (situation, action)],
                   "evidence": [{"round": point["round"], "frame": point["frame"], "line": point["evidence"][0]["line"]}
                                for point in points if (point["situation"], point["actual"]) == (situation, action)]}
                  for (situation, action), count in counts.most_common(3)]
        if not points:
            limitations.append("No attributable human decision-point events are available")
        highlights = []
        for kind in ("human_throw_break", "human_block", "human_landed_hit"):
            moment = next((value for value in inspection["moments"] if value["kind"] == kind), None)
            if moment:
                highlights.append(f"{moment['description']} Evidence: round {moment['round']}, frame {moment['frame']}, JSONL line {moment['evidence'][0]['line']}.")
        report = {
            "session_id": session_id, "generated_at": datetime.now(timezone.utc).isoformat(),
            "result": metadata.get("result") or "unknown", "habits": habits, "decision_points": points,
            "went_well": highlights,
            "drills": [f"Review {habit['situation']} at round {habit['evidence'][0]['round']}, frame {habit['evidence'][0]['frame']}; compare the recorded {habit['action']} with the available candidates in practice."
                       for habit in habits],
            "synthetic": synthetic, "limitations": limitations,
            "source": {"recording": str(path.relative_to(self.data_dir)), "record_counts": dict(recording.counts),
                       "tactical_sources": inspection["tactical_sources"]},
            "unattributed_decisions": [moment for moment in inspection["moments"]
                                       if moment["event_kind"] == "decision_point" and moment["kind"] == "unattributed_event"],
            "scoring_summary": {"scored": len(scores), "unavailable": len(points) - len(scores)},
        }
        REPORT_VALIDATOR.validate(report)
        await asyncio.to_thread(self.save, session_id, report)
        return report

    def save(self, session_id, report):
        destination = within(self.data_dir, self.data_dir / "reports" / f"{checked_id(session_id)}.json")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                             prefix=".report-", suffix=".tmp", delete=False) as output:
                temporary = Path(output.name)
                json.dump(report, output, ensure_ascii=False, allow_nan=False, indent=2)
                output.write("\n")
            os.replace(temporary, destination)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    def get(self, session_id):
        path = within(self.data_dir, self.data_dir / "reports" / f"{checked_id(session_id)}.json")
        report = json.loads(path.read_text(encoding="utf-8"))
        if not REPORT_VALIDATOR.is_valid(report) or report["session_id"] != session_id:
            raise ValueError("Saved report is invalid or has a mismatched session ID")
        return report
