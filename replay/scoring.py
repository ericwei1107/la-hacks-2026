import asyncio
import json
import math
import os

import httpx


class JevScorer:
    def __init__(self, api_key="", model="jev-latest", transport=None):
        self.api_key = api_key
        self.model = model
        self.transport = transport

    @classmethod
    def from_env(cls):
        mode = os.getenv("KUMITE_JEV_MODE", "auto").strip().lower()
        if mode not in {"auto", "local"}:
            raise ValueError("KUMITE_JEV_MODE must be auto or local")
        if mode == "local":
            return cls()
        return cls(os.getenv("TYPESAFE_API_KEY") or os.getenv("JEV_API_KEY", ""),
                   os.getenv("JEV_MODEL", "jev-latest"))

    async def score(self, items):
        if not self.api_key:
            return {}, "Jev API key is not configured"
        results = {}
        async with httpx.AsyncClient(transport=self.transport, timeout=20) as client:
            for offset in range(0, len(items), 12):
                batch = items[offset:offset + 12]
                state, questions = {}, {}
                for identifier, moment, options in batch:
                    state[identifier] = {key: moment.get(key) for key in (
                        "round", "frame", "situation", "context", "recorded_frame_advantage",
                        "frame_advantage_perspective", "missing_information")}
                    questions[identifier] = {
                        "type": "choice",
                        "instructions": (
                            f"For decision {identifier} in the supplied state, which human response is "
                            "most appropriate among these candidates? Consider only this decision's "
                            "recorded context. The snapshot may already reflect the action's outcome. "
                            "Range, move identity and frame advantage may be unknown. "
                            "Do not assume a guaranteed punish, successful outcome or optimality beyond "
                            "these candidates. Return a preference distribution, not hit or win chances."),
                        "criteria": {option["id"]: f"{option['name']}: {option['description']} ({option['command']})"
                                     for option in options},
                    }
                try:
                    async with asyncio.timeout(22):
                        response = await client.post(
                            "https://api.typesafe.ai/v1/systemone",
                            headers={"Authorization": f"Bearer {self.api_key}"},
                            json={"model": self.model, "state": json.dumps(state), "questions": questions})
                        response.raise_for_status()
                        payload = response.json()
                    answers = payload.get("answers", {}) if isinstance(payload, dict) else {}
                    for identifier, _, options in batch:
                        answer = answers.get(identifier) if isinstance(answers, dict) else None
                        if valid_answer(answer, {option["id"] for option in options}):
                            results[identifier] = {**answer, "model": payload.get("model", self.model)}
                except (httpx.HTTPError, TimeoutError, ValueError):
                    continue
        return results, "Jev returned no valid score for this decision (request failed or response was invalid)"


def valid_answer(answer, identifiers):
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        return False
    probabilities = answer.get("probabilities")
    if not isinstance(probabilities, dict) or set(probabilities) != identifiers:
        return False
    values = list(probabilities.values())
    if not all(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1 for value in values):
        return False
    choice = answer.get("choice")
    if not isinstance(choice, str) or choice not in probabilities:
        return False
    if not math.isclose(sum(values), 1, abs_tol=0.001) or probabilities[choice] != max(values):
        return False
    confidence = answer.get("confidence")
    return confidence is None or (type(confidence) in (int, float) and math.isfinite(confidence)
                                  and 0 <= confidence <= 1)
