import asyncio
import hashlib
import json
import math
import re
from collections import Counter

import httpx
from jsonschema import Draft202012Validator

from replay import coachvoice
from replay.character_data import CharacterDataError, MOVE_ALIASES, load_character, normalize_character
from replay.config import ROOT
from replay.evidence import decision_fingerprint
from replay.evidence_pack import set_pack
from replay.inspection import build_inspection
from replay.learning import finite_numbers, latest_mastery
from replay.move_coaching import labeled_move
from replay.options import generate_options
from replay.reader import read_recording
from replay.reports import within
from replay.tips import MIN_N, rank, topic_label

METRICS = Draft202012Validator(json.loads((ROOT / "contracts/metrics.schema.json").read_text()))


def tool(name, description, properties=None, required=None):
    return {"type": "function", "name": name, "description": description, "strict": False,
            "parameters": {"type": "object", "properties": properties or {},
                           "required": required or [], "additionalProperties": False}}


TEXT = {"type": "string", "maxLength": 120}
ROUND = {"type": "integer", "minimum": 1}
FRAME = {"type": "integer", "minimum": 0}
TOOL_DEFS = [
    tool("get_practice", "Evidence-backed practice priorities and drills, not learner scores.", {"situation": TEXT}),
    tool("get_habits", "Observed human action frequencies; not automatically weaknesses.", {"situation": TEXT}),
    tool("get_mastery", "Latest recorded local learner estimates, with missing-data limitations.", {"situation": TEXT}),
    tool("find_moments", "Find original recording events and any validated saved Jev preference.",
         {"situation": TEXT, "round": ROUND, "limit": {"type": "integer", "minimum": 1, "maximum": 5}}),
    tool("get_state_at", "Exact recorded state; round is required because frame counters reset.",
         {"round": ROUND, "frame": FRAME}, ["round", "frame"]),
    tool("get_frame_data", "Verified move names and character frame data for this set's characters.",
         {"character": TEXT, "move": TEXT}, ["character", "move"]),
    tool("list_punishers", "Character-data practice candidates for a hypothetical punish window; not proof of a recorded punish.",
         {"character": TEXT, "frames": {"type": "integer", "minimum": 10, "maximum": 20},
          "crouching": {"type": "boolean"}}, ["character", "frames"]),
    tool("get_learning_curve", "Read analytics GET /learning/{session} on port 8767; local latest-estimate fallback.",
         {"session": {"type": "string", "maxLength": 180}, "situation": TEXT}, ["session"]),
    tool("get_combos", "Reliable combo routes from the human's character data, to verify in Practice.", {"character": TEXT}),
]
VALIDATORS = {entry["name"]: Draft202012Validator(entry["parameters"]) for entry in TOOL_DEFS}
PRACTICE_DRILLS = {
    "after_block": "In Practice, block that move and hold guard through the follow-up before pressing.",
    "sidestep_dir": "In Practice, sidestep that move as it starts, then punish.",
    "neutral": "In Practice, set the dummy to that move and block it until the punish is automatic.",
    "whiff_punish": "In Practice, hold your ground until the opponent whiffs, then punish.",
    "missed_punish": "In Practice, block that move on repeat and punish it every time.",
}


def words(value):
    return str(value).replace("_", " ")


def question_situation(question):
    if re.search(r"\blows?\b|low_defense", question):
        return "low_defense"
    if re.search(r"\bthrows?\b|\bbreaks?\b|throw_break", question):
        return "throw_break"
    if re.search(r"after[ _-]block", question):
        return "after_block"
    if "sidestep" in question:
        return "sidestep_dir"
    return ""


def asks_about_practice_results(question):
    question = question.lower()
    return bool(re.search(r"^\s*(?:did|has|have|is|was|were)\b", question)
                and re.search(r"\bpracti[cs](?:e|ing)\b", question)
                and re.search(r"\b(?:help(?:ed|ing)?|work(?:ed|ing)?)\b", question))


def asks_for_practice(question):
    question = question.lower()
    if (asks_about_practice_results(question)
            or re.search(r"^\s*(?:have i|am i|did (?:i|my|practi[cs]ing)|has (?:my|practi[cs]ing)|is my|show (?:my )?(?:mastery|learning|progress))\b", question)):
        return False
    return bool(re.search(r"\b(?:advice|drills?|tips|practi[cs]e)\b", question)
                or re.search(r"\b(?:how|what)\b.*\b(?:beat|deal with|handle|counter|stop|fight|win against)\b", question)
                or re.search(r"\bwhat (?:should|can|do) i do\b", question)
                or re.search(r"\b(?:how|what)\b.*\b(?:can|could|should|do)\s+i\b.*\b(?:improve|work on|get better|do better)\b", question)
                or re.search(r"\bhow to (?:improve|get better)\b", question)
                or re.search(r"\bi (?:want|need|would like) to (?:improve|get better)\b", question)
                or re.search(r"\bhelp me (?:improve|get better)\b", question))


class ChatTools:
    def __init__(self, reports, session, analytics_url, analytics_transport=None):
        self.reports = reports
        self.session = session
        self.analytics_url = analytics_url.rstrip("/")
        self.analytics_transport = analytics_transport
        self.facts = {}
        self.calls = 0
        self.practice_ids = set()

    def load(self):
        path = self.reports.locate(self.session)
        recording = read_recording(path)
        if recording.session_id != self.session or not all(finite_numbers(row.data) for row in recording.records):
            raise ValueError("Invalid recording session or numeric data")
        self.recording = recording
        self.inspection = build_inspection(recording)
        self.coordinates = {(row.data["round"], row.data["frame"]) for row in recording.records if "frame" in row.data}
        self.states, self.ambiguous_coordinates = {}, set()
        for row in recording.records:
            if row.data["t"] != "state":
                continue
            coordinate = (row.data["round"], row.data["frame"])
            if coordinate in self.states and self.states[coordinate] != row.data:
                self.ambiguous_coordinates.add(coordinate)
            self.states[coordinate] = row.data
        self.decisions = [moment for moment in self.inspection["moments"] if moment["kind"] == "human_decision"
                          and moment["context"] and moment["context"]["age_frames"] == 0
                          and (moment["round"], moment["frame"]) not in self.ambiguous_coordinates]
        self.characters = set()
        self.human = self.bot = None
        for state in self.states.values():
            players = {player["slot"]: player for player in state["players"]}
            self.human = players[state["human_slot"]]["character"]
            self.bot = players[1 - state["human_slot"]]["character"]
            self.characters.update(player["character"] for player in state["players"])
        self.report = None
        self.report_note = "No saved scored report is available; recorded observations are still available."
        try:
            report = self.reports.get(self.session)
            if finite_numbers(report):
                self.report = report
                self.report_note = ""
        except (FileNotFoundError, ValueError):
            pass
        metadata = self.reports.metadata(self.session, path, [])
        self.synthetic = "synthetic" in path.parts or metadata.get("mode") == "synthetic"
        self.last_round = max(row.data["round"] for row in recording.records)
        return self

    def fact(self, text, citations=None):
        if len(text) > 1600:
            text = "That evidence is too long to quote reliably in a brief answer. Please ask about a more specific moment or situation."
        citations = citations or []
        if any((value["round"], value["frame"]) not in self.coordinates for value in citations):
            raise ValueError("Citation is not a recorded coordinate")
        payload = {"text": text, "citations": citations}
        identifier = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
        fact = {"id": identifier, **payload}
        self.facts[identifier] = fact
        return fact

    async def call(self, name, arguments):
        self.calls += 1
        if self.calls > 8:
            return {"error": "Tool-call limit reached", "facts": [self.fact("The evidence lookup limit was reached; additional details are unavailable.")]}
        validator = VALIDATORS.get(name)
        if validator is None or not isinstance(arguments, dict) or not validator.is_valid(arguments):
            return {"error": "Unknown tool or invalid arguments", "facts": [self.fact("That request could not be verified. Please specify a valid recorded round, frame, situation or move.")]}
        if name == "get_learning_curve" and arguments["session"] != self.session:
            return {"error": "Tools are scoped to the selected session", "facts": [self.fact("I can only use evidence from the selected set.")]}
        try:
            if name == "get_learning_curve":
                facts = await self.get_learning_curve(situation=arguments.get("situation", ""))
            else:
                facts = await asyncio.to_thread(getattr(self, name), **arguments)
            return {"facts": facts}
        except (CharacterDataError, ValueError, OSError, KeyError, TypeError):
            return {"facts": [self.fact("That information is unavailable or could not be uniquely verified for this set.")]}

    def get_habits(self, situation=""):
        points = [point for point in self.decisions if point["human_action"] and point["situation"]
                  and (not situation or situation in point["situation"])]
        counts = Counter((point["situation"], point["human_action"]) for point in points)
        totals = Counter(point["situation"] for point in points)
        facts = []
        pack = self.set_evidence()
        candidates = coachvoice.ranked(pack)
        for (label, action), count in counts.most_common(4):
            related = [point for point in points if (point["situation"], point["human_action"]) == (label, action)]
            cites = [{"round": point["round"], "frame": point["frame"]} for point in related[:2]]
            text = (f"{coachvoice.situation_phrase(label).capitalize()} you {coachvoice.action_phrase(label, action)} "
                    f"{count} of {totals[label]} times. {coachvoice.habit_fix(pack, label, action, candidates)}")
            facts.append(self.fact(text, cites))
        return facts or [self.fact("No attributable labeled human decisions are available for that situation; bot choices do not identify human actions.")]

    def set_evidence(self):
        if not hasattr(self, "_pack"):
            self._pack = None
            try:
                raw = [point["evidence"][0]["record"] for point in self.decisions]
                self._pack = set_pack(self.recording.records, decisions=raw)
            except (CharacterDataError, ValueError, OSError, KeyError, TypeError):
                self._pack = None
        return self._pack

    def get_practice(self, situation=""):
        points = [point for point in self.decisions if not situation or situation in (point["situation"] or "")]
        entries = {}
        for label, action, priority, drill in [
            ("low_defense", "hit", "low blocking",
             "In Practice, work on crouch-blocking predictable lows, then returning to standing guard."),
            ("throw_break", "none", "throw breaks",
             "In Practice, rehearse recognizing throws and using the matching break input."),
        ]:
            related = [point for point in points if point["situation"] == label]
            matching = [point for point in related if point["human_action"] == action]
            if len(matching) < MIN_N or len(matching) / len(related) < 0.6:
                continue
            observation = (f"{coachvoice.bot_label(self.set_evidence())}'s lows caught you {len(matching)} of {len(related)} times."
                           if label == "low_defense" else
                           f"You did not break {len(matching)} of {len(related)} throws.")
            citations = [{"round": point["round"], "frame": point["frame"]} for point in matching[:2]]
            entries[label] = {"priority": priority, "observation": observation, "answer": "", "drill": drill,
                              "citations": citations, "damage": 0, "count": len(matching)}
        pack = self.set_evidence()
        wanted = situation.split(":", 1)[0] if situation else ""
        for candidate in (rank(pack) if pack else []):
            if wanted and candidate.topic != wanted:
                continue
            entry = entries.get(candidate.topic)
            if entry is None:
                entries[candidate.topic] = {"priority": topic_label(candidate.topic), "observation": "", "answer": candidate.text,
                                            "drill": PRACTICE_DRILLS.get(candidate.topic, ""), "citations": list(candidate.citations[:2]),
                                            "damage": candidate.damage, "count": candidate.numbers[0] if candidate.numbers else 0}
            else:
                entry["answer"] = candidate.text
                entry["damage"] = candidate.damage
        ordered = sorted(entries.values(), key=lambda entry: (entry["damage"], entry["count"]), reverse=True)
        facts = []
        for index, entry in enumerate(ordered[:3]):
            lead = ("Start with", "Next, work on", "Then work on")[index]
            text = " ".join(f"{lead} {entry['priority']}. {entry['observation']} {entry['answer']} {entry['drill']}".split())
            try:
                facts.append(self.fact(text, entry["citations"]))
            except ValueError:
                facts.append(self.fact(text))
        if facts:
            return facts
        citations = [{"round": point["round"], "frame": point["frame"]} for point in points[:2]]
        review = ("Review the cited exchanges in Practice, or record another short set."
                  if citations else "Record a short set with repeated blocking and throw situations, then ask again.")
        return [self.fact("There are not enough repeated, attributable decisions to pick a specific drill yet. " + review, citations)]

    def get_combos(self, character=""):
        name = normalize_character(character) if character else self.human
        if name is None or name != self.human:
            return [self.fact("Combos come from the recorded human's character only.")]
        facts = [self.fact(text) for text in coachvoice.combos(name)]
        return facts or [self.fact("No combo routes are listed for that character.")]

    def get_mastery(self, situation=""):
        path = within(self.reports.data_dir, self.reports.data_dir / "learning" / f"{self.session}.jsonl")
        mastery, warnings = latest_mastery(path, self.session, self.last_round)
        caveat = " " + " ".join(warnings) if warnings else ""
        matching = [(label, estimate) for label, estimate in mastery.items() if not situation or situation in label]
        facts = [self.fact(f"The learner's latest valid {words(label)} mastery estimate is {estimate['mastery']:.3g}, "
                           f"from round {estimate['round']}'s recorded learning snapshot. "
                           "This is a model estimate, not proof of improvement." + caveat)
                 for label, estimate in matching[:5]]
        if warnings:
            facts.append(self.fact(" ".join(warnings[:2]) + ". Improvement cannot be confirmed from missing or invalid learning data."))
        return facts or [self.fact("Learning mastery is unavailable for the requested situation; improvement cannot be confirmed.")]

    def saved_preference(self, moment):
        if (self.report is None or not moment["human_action"] or not moment["context"]
                or moment["context"]["age_frames"] != 0
                or (moment["round"], moment["frame"]) in self.ambiguous_coordinates):
            return None
        match = next((point for point in self.report["decision_points"]
                      if (point["round"], point["frame"], point["actual"], point["situation"]) ==
                      (moment["round"], moment["frame"], moment["human_action"], moment["situation"])), None)
        if not match or match.get("scoring", {}).get("status") != "scored" or not match["options"]:
            return None
        generated = generate_options(moment["context"]["human"]["character"], moment)
        if match.get("evidence_fingerprint") != decision_fingerprint(moment, generated["options"]):
            return None
        allowed = {(option["name"], option["command"]) for option in generated["options"]}
        pairs = [(option["name"], option.get("command", "")) for option in match["options"]]
        probabilities = [option["p"] for option in match["options"]]
        if (set(pairs) != allowed or len(set(pairs)) != len(pairs)
                or not all(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1 for value in probabilities)
                or not math.isclose(sum(probabilities), 1, abs_tol=0.001)):
            return None
        chosen = [option for option in match["options"] if option["name"] == match["best"]]
        if len(chosen) != 1 or chosen[0]["p"] != max(probabilities):
            return None
        explanation = (f"At round {moment['round']}, frame {moment['frame']}, the saved Jev analysis preferred "
                         f"{chosen[0]['name']} among its candidates, with preference {chosen[0]['p']:.3g}. "
                         "This is not a hit or win probability, a guaranteed punish, or proof the recorded choice was wrong. "
                         + " ".join(generated["limitations"]))
        if len(explanation) > 1600:
            explanation = "The saved Jev preference has unresolved candidate limitations; I cannot give a reliable short recommendation for it."
        return self.fact(explanation, [{"round": moment["round"], "frame": moment["frame"]}])

    def find_moments(self, situation="", round=None, limit=3):
        moments = [moment for moment in self.inspection["moments"]
                   if (not situation or situation in (moment["situation"] or ""))
                   and (round is None or moment["round"] == round)]
        if not moments:
            return [self.fact("No matching recorded moments are available; an action or outcome cannot be inferred.")]
        facts = []
        has_preference = False
        for moment in moments[:limit]:
            confident = (moment["context"] and moment["context"]["age_frames"] == 0
                         and (moment["round"], moment["frame"]) not in self.ambiguous_coordinates)
            if moment["event_kind"] == "decision_point":
                raw = moment["evidence"][0]["record"]
                human = confident and moment["kind"] == "human_decision"
                role = "the human's" if human else f"slot {raw.get('actor', 'unknown')}'s"
                if human and moment["situation"] and raw.get("action"):
                    description = (f"{coachvoice.situation_phrase(moment['situation']).capitalize()} you "
                                   f"{coachvoice.action_phrase(moment['situation'], raw['action'])} (labeled '{raw['action']}').")
                else:
                    description = f"The recorder labeled {role} response as '{raw.get('action') or 'unknown'}' for {words(moment['situation'] or 'unknown situation')}."
                if not human:
                    description += " Human attribution is uncertain because exact state context is unavailable or conflicting."
            elif not confident:
                raw = moment["evidence"][0]["record"]
                description = (f"The recorder logged a {moment['event_kind']} event with actor slot {raw.get('actor', 'unknown')} "
                               f"and target slot {raw.get('target', 'unknown')}. Human attribution is uncertain because exact state context is unavailable or conflicting.")
            else:
                description = moment["description"]
            facts.append(self.fact(f"Round {moment['round']}, frame {moment['frame']}: {description}",
                                   [{"round": moment["round"], "frame": moment["frame"]}]))
            preference = self.saved_preference(moment)
            if preference:
                facts.append(preference)
                has_preference = True
        if self.report_note:
            facts.append(self.fact(self.report_note))
        elif not has_preference:
            facts.append(self.fact("No validated saved Jev preference is available for these matching moments."))
        return facts or [self.fact("No matching recorded moments are available; an action or outcome cannot be inferred.")]

    def get_state_at(self, round, frame):
        if (round, frame) in self.ambiguous_coordinates:
            return [self.fact(f"Conflicting snapshots were recorded at round {round}, frame {frame}; an exact state cannot be established.")]
        state = self.states.get((round, frame))
        if state is None:
            return [self.fact(f"No exact state is recorded at round {round}, frame {frame}. A nearby state would not prove what happened there.")]
        players = {player["slot"]: player for player in state["players"]}
        human, opponent = players[state["human_slot"]], players[1 - state["human_slot"]]
        return [self.fact(f"At round {round}, frame {frame}, the human had {human['health']} health and the opponent had "
                          f"{opponent['health']}. The recorded distance bucket was {state['derived'].get('distance_bucket', 'unknown')}. "
                          "These health values do not establish avoidable damage.", [{"round": round, "frame": frame}])]

    def get_frame_data(self, character, move):
        name = normalize_character(character)
        if name not in self.characters:
            return [self.fact("That character is not verified in the selected recording.")]
        data = load_character(name)
        resolved = labeled_move(data, move)
        if resolved is None:
            return [self.fact("That move could not be uniquely verified in the character data; unknown or shared IDs are not guessed.")]
        label = data.label(resolved)
        startup, advantage = resolved.get("startup"), resolved.get("on_block")
        description = f"Character data lists {words(name)}'s {label} ({resolved['command']}) as {resolved.get('hit_level', 'unknown level')}."
        if type(startup) is int:
            description += f" Startup is {startup} frames."
        if type(advantage) is int:
            description += f" Its on-block value is {advantage:+d}."
        opponent_move = name == self.bot and name != self.human
        if opponent_move and type(advantage) is int and advantage > 0:
            description += " Practice guarding before pressing after it."
        elif opponent_move and resolved.get("hit_level") == "low":
            description += " Practice recognizing and crouch-blocking it."
        description += " This listing does not establish timing, range or a punish in a recorded exchange."
        return [self.fact(description)]

    def list_punishers(self, character, frames, crouching=False):
        name = normalize_character(character)
        if name != self.human:
            return [self.fact("Punisher practice candidates must come from the recorded human's character.")]
        data = load_character(name)
        entries = data.punish_tier(-frames, crouching=crouching)
        commands = [entry.get("command") if isinstance(entry, dict) else entry for entry in entries]
        candidates = [data.label(data.by_command[command]) + f" ({command})" for command in commands if command in data.by_command]
        if not candidates:
            return [self.fact("No verified punisher is listed for that hypothetical window.")]
        return [self.fact(f"For a hypothetical {frames}-frame {'crouching' if crouching else 'standing'} window, character data lists "
                          + ", ".join(candidates[:3]) + ". These are practice candidates; actual range, timing and string completion are unverified.")]

    async def get_learning_curve(self, situation=""):
        try:
            async with asyncio.timeout(1.2):
                async with httpx.AsyncClient(timeout=1, transport=self.analytics_transport, follow_redirects=False) as client:
                    response = await client.get(f"{self.analytics_url}/learning/{self.session}")
                    response.raise_for_status()
                    metrics = response.json()
            if not METRICS.is_valid(metrics) or not finite_numbers(metrics) or metrics["session_id"] != self.session:
                raise ValueError("Invalid learning metrics")
            rows = [row for row in metrics["rounds"] if row["round"] <= self.last_round]
            if any(row.get("session_id", self.session) != self.session for row in rows):
                raise ValueError("Learning session mismatch")
            labels = sorted({label for row in rows for label, habit in row["habits"].items()
                             if "mastery" in habit and (not situation or situation in label)})
            facts = []
            for label in labels[:4]:
                values = [f"round {row['round']}: {row['habits'][label]['mastery']:.3g}" for row in sorted(rows, key=lambda item: item["round"])
                          if label in row["habits"] and "mastery" in row["habits"][label]]
                facts.append(self.fact(f"Analytics reports {words(label)} learner mastery estimates of " + "; ".join(values[-6:])
                                       + ". These estimates alone do not confirm improvement."))
            return facts or [self.fact("Analytics has no matching mastery estimates for the recorded rounds.")]
        except (httpx.HTTPError, httpx.InvalidURL, ValueError, TimeoutError):
            return [self.fact("The analytics learning curve is unavailable; I can only check local recorded estimates."), *self.get_mastery(situation)]

    async def initial(self, request):
        practice = asks_for_practice(request.message)

        def answer(facts):
            if practice:
                self.practice_ids = {fact["id"] for fact in facts}
            return facts

        question = request.message
        if len(question.split()) < 6:
            previous = [entry.text for entry in request.history if entry.role == "user"]
            if previous:
                question = previous[-1] + " " + question
        lowered = question.lower()
        situation = question_situation(request.message.lower()) or question_situation(lowered)
        if not practice and (asks_about_practice_results(request.message)
                             or any(token in lowered for token in ("mastery", "improv", "learning", "progress", "better", "fixed"))):
            facts = (await self.call("get_learning_curve", {"session": self.session, "situation": situation}))["facts"]
            story = coachvoice.progression(self.set_evidence(), situation)
            if story:
                facts = [self.fact(story)] + facts
            return facts[:3]
        round_match = re.search(r"\bround\s+(\d+)\b", lowered)
        frame_match = re.search(r"\bframe\s+(\d+)\b", lowered)
        if frame_match:
            if not round_match:
                return answer([self.fact("Frame counters reset each round. Please include the round as well as the frame.")])
            return answer((await self.call("get_state_at", {"round": int(round_match[1]), "frame": int(frame_match[1])}))["facts"])
        characters = (self.human,) if re.search(r"\bmy\b", lowered) else (self.bot, self.human)
        mentioned = [name for name in self.characters if name.replace("_", " ") in lowered or name in lowered]
        if len(mentioned) == 1:
            characters = mentioned
        explicit_move = re.search(r"\b(my|his|their|opponent's)\s+move\s+(.+?)[?.!]*$", lowered)
        if explicit_move:
            character = self.human if explicit_move[1] == "my" else self.bot
            return answer((await self.call("get_frame_data", {"character": character or "unknown", "move": explicit_move[2].strip()}))["facts"])
        if re.search(r"\bcombos?\b|\bjuggles?\b", lowered):
            facts = (await self.call("get_combos", {"character": self.human or "unknown"}))["facts"][:1]
            if practice:
                facts += (await self.call("get_practice", {"situation": situation}))["facts"][:2]
            return answer(facts)
        for character in characters:
            if not character or normalize_character(character) is None:
                continue
            try:
                data = load_character(character)
            except (CharacterDataError, OSError, ValueError):
                continue
            queries = list(MOVE_ALIASES.get(character, {})) + [move["name"] for move in data.moves if move.get("name")]
            queries += [move["command"] for move in data.moves if len(move["command"]) > 2]
            for query in sorted(set(queries), key=len, reverse=True):
                pattern = r"(?<![\w])" + re.escape(query.lower()) + r"(?![\w])"
                compact_command = re.sub(r"[^a-z0-9]", "", query.lower())
                compact_pattern = r"\b" + re.escape(compact_command) + r"\b"
                if re.search(pattern, lowered) or (re.search(r"[a-z]", compact_command) and len(compact_command) > 1 and re.search(compact_pattern, lowered)):
                    return answer((await self.call("get_frame_data", {"character": character, "move": query}))["facts"])
        if practice:
            return answer((await self.call("get_practice", {"situation": situation}))["facts"])
        if any(token in lowered for token in ("moment", "decision", "happen", "why", "round", "score", "jev")):
            args = {"situation": situation, "limit": 2}
            if round_match:
                args["round"] = int(round_match[1])
            return (await self.call("find_moments", args))["facts"][:3]
        if any(token in lowered for token in ("move", "against")) and not situation:
            return [self.fact("I could not uniquely identify that move. Please give its command or verified name.")]
        return (await self.call("get_habits", {"situation": situation}))["facts"][:3]
