import hashlib
import json


def decision_fingerprint(moment, options):
    payload = {
        "version": "kumite.decision.v1",
        "decision": {key: moment.get(key) for key in (
            "round", "frame", "situation", "human_slot", "human_action", "context",
            "recorded_frame_advantage", "frame_advantage_perspective", "missing_information",
            "evidence")},
        "candidates": [{key: option[key] for key in ("id", "name", "command", "description")}
                       for option in options],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
