# Learning screen specs

Design: `learning-design.md`

## Hero and chart

- [ ] **MAIN-LEARNING-001**: The Learning screen shall show, in the display face, the prediction accuracy of the last round of the selected set that has a non-null accuracy, followed by "of your next moves the bot guessed right in round <n>." and "Round 1: <first accuracy>."
- [ ] **MAIN-LEARNING-006**: The hero accuracy shall fit within its 380 px column, at 140 px for one or two digits and 120 px for 100%.
- [ ] **MAIN-LEARNING-002**: The Learning screen shall frame in `--color-primary` a line chart titled "How often the bot guessed your next move" with one point per round that has an accuracy, rounds labelled R1 to Rn in mono, and gridlines every 10 percentage points spanning the data.
- [ ] **MAIN-LEARNING-003**: The accuracy chart shall fill and label the last point with its value.
- [ ] **MAIN-LEARNING-004**: The accuracy chart shall mark each round flagged `player_changed` with a dashed `--color-bot` line labelled "you adapted".
- [ ] **MAIN-LEARNING-005**: The accuracy chart shall mark the round where the earliest-detected habit was detected with "Spotted your <habit short form> habit".

## This set

- [ ] **MAIN-LEARNING-010**: The Learning screen shall show the earliest detection as "<n> rounds" and "to spot your <habit short form> habit", where the habit has the lowest `time_to_detect` and ties go to the habit listed first.
- [ ] **MAIN-LEARNING-011**: The Learning screen shall show the habits fixed in the last round but not in the first as "<k> black belt" (or "belts") and "earned this set: <habit names>", or "No black belt yet" and "earned this set" when there are none.
- [ ] **MAIN-LEARNING-012**: When the last round has bandit data, the Learning screen shall show "When the bot went for your habit" with one meter per option of the bandit entry for the targeted habit's situation, or of the first entry if none matches.

## Habits table

- [ ] **MAIN-LEARNING-020**: The habits table shall show one row per habit of the last round, with its belt, its name, its rank name, a belt square per round for the last six rounds under the heading "How well you've learned the right answer, R<a> to R<b>", its rounds to detect, and its rounds to master, writing an em dash where a value is missing.
- [ ] **MAIN-LEARNING-021**: When a habit's situation appears in the `exploited` list of the selected set's last round summary, its row shall add ". The habit the bot is attacking right now." to the rank name and draw that line in `--color-bot`.
- [ ] **MAIN-LEARNING-022**: The habits table shall order rows with targeted habits first, then by mastery from lowest.
- [ ] **MAIN-LEARNING-024**: Each habits table row shall be at least 56 px tall and grow to fit a rank line that wraps.
- [ ] **MAIN-LEARNING-023**: When a habit has a `time_to_mastery` but is not `fixed` in the last round, its row shall add "Fixed in round <time to mastery>, slipped since." to the rank line and show its to-master value in `--color-text-muted`.

## States

- [ ] **MAIN-LEARNING-030**: While the learning metrics are loading for the first time, the Learning screen shall show the Paper loading skeleton.
- [ ] **MAIN-LEARNING-031**: While the brain lists no sets, the Learning screen shall show the empty state "Nothing to learn from yet." with "Play a set against Kumite and the learning panel fills in round by round."
- [ ] **MAIN-LEARNING-032**: When the learning metrics have no rounds, the Learning screen shall show the empty state "Round 1 is still going." with "Learning shows up when the round ends."
- [ ] **MAIN-LEARNING-033**: While analytics is offline, the Learning screen shall show the offline banner for analytics above any metrics it already holds.
- [ ] **MAIN-LEARNING-035**: While the frame is waiting for round <n> of the selected set and the learning metrics do not yet include round <n>, the Learning screen shall show "Round <n> is still being saved." in muted text under the page header, in place of the "Round 1 is still going." empty state when the metrics have no rounds.
- [ ] **MAIN-LEARNING-034**: While the brain is offline and analytics is not, the Learning screen shall show "Can't reach the brain." with "This is your last saved set. Live learning picks up when it reconnects." above the metrics.

## Implemented in

| Spec IDs | Entry point |
|---|---|
| MAIN-LEARNING-001 – MAIN-LEARNING-034 | `src/renderer/src/main-window/screens/Learning.tsx` (`Learning`, `LearningBody`, `AccuracyChart`, `Milestones`, `HabitsTable`) |
