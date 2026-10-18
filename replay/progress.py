from collections import defaultdict
from fractions import Fraction


TOPICS = {
    "low_defense": "blocking lows",
    "throw_break": "breaking throws",
    "sidestep_dir": "sidestepping",
    "after_block:any": "decisions after blocking",
    "after_block:bot_minus": "taking your turn after blocking",
    "after_block:bot_plus": "defending after blocking",
}


def topic(label):
    return TOPICS.get(label, "decisions after blocking" if label.startswith("after_block:") else "this response pattern")


def order(label):
    return list(TOPICS).index(label) if label in TOPICS else len(TOPICS)


def trend(values):
    directions = {1 if right > left else -1 if right < left else 0 for left, right in zip(values, values[1:])}
    if 1 in directions and -1 in directions:
        return "mixed"
    return "up" if 1 in directions else "down" if -1 in directions else "flat"


def estimate_progress(rows, situation=""):
    unique = {}
    for row in rows:
        if row["round"] in unique and unique[row["round"]] != row:
            raise ValueError("Conflicting learning snapshots for one round")
        unique[row["round"]] = row
    rows = sorted(unique.values(), key=lambda row: row["round"])
    if not rows:
        return []
    labels = sorted({label for row in rows for label, habit in row["habits"].items()
                     if "mastery" in habit and (not situation or situation in label)}, key=lambda label: (order(label), label))
    facts = []
    for label in labels[:2]:
        name = topic(label)
        values = [(row["round"], float(f"{row['habits'][label]['mastery']:.3g}")) for row in rows
                  if label in row["habits"] and "mastery" in row["habits"][label]]
        first, last = values[0], values[-1]
        if label not in rows[-1]["habits"] or "mastery" not in rows[-1]["habits"][label]:
            text = f"There is no current estimate for {name} in round {rows[-1]['round']}, so I cannot compare it reliably."
        elif len(values) == 1:
            text = (f"There is only one learning estimate for {name}, from round {last[0]} ({last[1]:.3g}). "
                    "I cannot compare rounds yet.")
        else:
            direction = trend([value for _, value in values])
            if direction == "flat":
                text = f"The learner's estimate for {name} stayed about the same, around {last[1]:.3g}, between round {first[0]} and round {last[0]}."
            elif direction == "mixed":
                text = (f"The learner's estimate for {name} went up and down between round {first[0]} and round {last[0]} "
                        f"({first[1]:.3g} to {last[1]:.3g}), rather than showing a steady improvement.")
            else:
                verb = "rose" if direction == "up" else "fell"
                text = f"The learner's estimate for {name} {verb} from {first[1]:.3g} in round {first[0]} to {last[1]:.3g} in round {last[0]}."
            text += " These estimates alone do not confirm improvement."
        facts.append({"text": text, "citations": []})
    return facts


def observed_progress(decisions, situation=""):
    facts = []
    for label in ("low_defense", "throw_break"):
        if situation and situation not in label:
            continue
        rounds = defaultdict(list)
        for point in decisions:
            if point["situation"] != label:
                continue
            action = point["human_action"]
            success = {"blocked": True, "hit": False}.get(action) if label == "low_defense" else None
            if label == "throw_break":
                evidence = point.get("evidence") or []
                detail = evidence[0].get("record", {}).get("detail", {}) if evidence else {}
                correct = detail.get("correct") if isinstance(detail, dict) else None
                success = correct if type(correct) is bool else False if action == "none" else None
            if success is not None:
                rounds[point["round"]].append((point, success))
        if len(rounds) < 2:
            continue
        numbers = sorted(rounds)
        counts = [(number, sum(success for _, success in rounds[number]), len(rounds[number])) for number in numbers][-6:]
        first, last = counts[0], counts[-1]
        direction = trend([Fraction(success, total) for _, success, total in counts])
        subject = "low blocking" if label == "low_defense" else "throw breaking"
        evidence = "labeled lows with known outcomes" if label == "low_defense" else "labeled throws with known outcomes"
        if direction == "mixed":
            lead = f"Your {subject} went up and down between rounds, rather than showing steady improvement."
        elif direction == "flat":
            lead = f"Your {subject} rate stayed the same across the compared rounds."
        else:
            share = "larger" if direction == "up" else "smaller"
            verb = "blocked" if label == "low_defense" else "broke"
            lead = f"You {verb} a {share} share of the {evidence}."
        shown = counts if direction == "mixed" else [first, last]
        examples = ", then ".join(f"{success} of {total} in round {number}" for number, success, total in shown)
        text = f"{lead} Among labeled decisions with known outcomes, the results were {examples}."
        text += " This describes the recorded exchanges, not proof of lasting improvement."
        cited = [rounds[first[0]][0][0], rounds[last[0]][-1][0]]
        facts.append({"text": text, "citations": [{"round": point["round"], "frame": point["frame"]} for point in cited]})
    return facts
