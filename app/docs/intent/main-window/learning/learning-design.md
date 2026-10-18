---
parent: main-window
prefix: MAIN-LEARNING
---

# Learning screen

## Context and Design Philosophy

The Learning screen is the proof that the bot learns, in numbers, and the closing shot of the demo video (HLD G4). Paper: the Learning artboard, plus Learning · Loading and Learning · Offline on the States page. One huge number leads: how much of the player's play the bot now predicts. The indigo frame holds the accuracy chart, because the rising line is the claim.

Its data is the analytics service's learning metrics for the selected set, plus the set's round summaries from the recording for the habit the bot is targeting.

## Hero

The last round with a prediction accuracy: its accuracy in the display face, sized to stay inside its 380 px column (a three-digit 100% is set smaller than two digits), then "of your next moves the bot guessed right in round <n>.", then "Round 1: <first>%." in muted. Rounds with a null accuracy are skipped.

## Accuracy chart

"How often the bot guessed your next move", framed in indigo. One point per round on a line, rounds R1 to Rn along the bottom in mono, gridlines every 10 points between the lowest and highest tens that contain the data. The last point is filled and labelled with its value. A dashed rust line marks each round flagged `player_changed`, labelled "you adapted". Under the round where the earliest-detected habit was spotted, an indigo marker reads "Spotted your <habit short form> habit".

## This set

- "<n> rounds" / "to spot your <habit short form> habit": the earliest detection, from `time_to_detect` (the habit with the lowest round; ties go to the habit listed first).
- Black belts earned this set: the habits fixed in the last round that were not fixed in the first, as "<k> black belt(s)" / "earned this set: <habit names>", or "No black belt yet" / "earned this set" when none.
- "When the bot went for your habit": the last round's bandit for the targeted habit's situation, or the first bandit entry if none matches, as one meter per option with its hit rate. The section is hidden when the last round has no bandit data.

## Habits table

One row per habit in the last round, with columns:

- The belt (design-system), the habit name, and its rank name ("Yellow belt, 1 stripe"). The habit the bot is targeting (named in the last round summary's `exploited`) adds ". The habit the bot is attacking right now." and its line turns rust.
- "How well you've learned the right answer, R<a> to R<b>": a belt square per round for the last six rounds. The belt is the player's mastery of the right response in that situation, so the squares are their learning curve for the habit.
- "To detect" and "To master" in rounds, or an em dash. A row grows when its rank line wraps. "To master" is history: how many rounds it took to first fix the habit. A habit can slip after that, so when a habit has a time to master but is not fixed in the last round, its rank line adds "Fixed in round <n>, slipped since." and its to-master number is muted. The belt and the "black belts earned this set" count always follow the last round.

Rows are ordered: the targeted habit first, then by mastery, lowest first.

## States

- **Round still saving:** after a round ends, the learning metrics can trail the round summary by a moment. While the frame is still waiting for that round, a muted line under the page header reads "Round <n> is still being saved."

- **Loading:** the Paper skeleton.
- **No sets:** the empty state "Nothing to learn from yet." / "Play a set against Kumite and the learning panel fills in round by round."
- **No rounds yet** (metrics with no rounds): the empty state "Round 1 is still going." / "Learning shows up when the round ends."
- **Offline:** the offline banner for analytics, or for the brain when only the brain is unreachable: "Can't reach the brain. This is your last saved set. Live learning picks up when it reconnects."

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Which habit is "your habit" | The earliest-detected habit | The habit with the lowest mastery; the bot's target | Paper pairs the detection marker and the "rounds to spot" number. Detection order is in the metrics; it does not need the recording. |
| The bot's target | From the recording's last round summary | Leaving it off the table | The design highlights it in rust. Only round summaries name the exploited habits, and the recording is already loaded for other screens. |
| Fine-tune before/after | Not shown | A row under "This set" | The Paper design leaves it out. The metrics carry it, so it can be added without a contract change once it exists. |

## References

- Paper file "Kumite — Tatami": Learning; States, Learning · Loading and Learning · Offline
- `../../../../../contracts/metrics.schema.json`
