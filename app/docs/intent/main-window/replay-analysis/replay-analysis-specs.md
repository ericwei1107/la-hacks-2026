# Replay analysis screen specs

Design: `replay-analysis-design.md`

## Top habit

- [ ] **MAIN-REPLAY-001**: When the selected set's report has at least one habit, the Replay analysis screen shall frame the first habit in `--color-primary`, showing "Your top habit, and the smallest fix for it" over the habit's `min_change` in the display face.
- [ ] **MAIN-REPLAY-002**: The top habit shall show the sentence "You did this in <p as whole percent>% of these spots, <count> times this set."
- [ ] **MAIN-REPLAY-003**: The top habit shall show as "damage lost to this habit" the sum of `cost` over the report's decision points whose `frame` is in the habit's `moments`.
- [ ] **MAIN-REPLAY-004**: When the best option of the decision point at the habit's first moment has a command starting with a direction, the top habit shall draw a 3 × 3 direction pad with that direction's cell filled.
- [ ] **MAIN-REPLAY-005**: The top habit shall label that best option's command "hold <command>" when the command is a direction alone and "press <command>" otherwise, and shall show no move when no such option exists.

## Situation filter

- [ ] **MAIN-REPLAY-010**: The Replay analysis screen shall show an "All" chip with the number of decision points, followed by one chip per distinct decision-point `situation`, in order of first appearance, each with its count.
- [ ] **MAIN-REPLAY-011**: When the player selects a situation chip, the screen shall show only the decision points with that `situation`, and the "All" chip shall show all of them.

## Decision points

- [ ] **MAIN-REPLAY-020**: The screen shall show the filtered decision points in report order with the first expanded and the others collapsed.
- [ ] **MAIN-REPLAY-021**: When the player activates a collapsed decision point, the screen shall expand it and collapse the one that was expanded.
- [ ] **MAIN-REPLAY-022**: An expanded decision point shall show "Round <r>, frame <f>", the situation, its cost as "<cost> damage", "You did" with the actual option, "Best option" with the best option and its command, one meter per option with its percentage (the best first, in `--color-primary`, the others in `--color-text-muted`), "your pick" beside the actual option, and "Why" with the explanation.
- [ ] **MAIN-REPLAY-023**: A collapsed decision point not marked `good` shall show "<actual>. Best: <best>" and "−<cost>".
- [ ] **MAIN-REPLAY-024**: A collapsed decision point marked `good` shall show a check and "<actual>. Right call" and "+<cost>", all in green.
- [ ] **MAIN-REPLAY-025**: The screen shall show at most four decision points of the current filter until the player activates "Show <n> more in this situation", which shows the rest.
- [ ] **MAIN-REPLAY-026**: When the screen opens with a focus of round and frame, it shall select "All", show every decision point, and expand the one at that round and frame if one exists.
- [ ] **MAIN-REPLAY-027**: The screen shall write an option as its name in words followed by its command in notation in parentheses when the option has a command.

## States

- [ ] **MAIN-REPLAY-030**: While the report is loading for the first time, the screen shall show a skeleton top habit and skeleton rows.
- [ ] **MAIN-REPLAY-031**: When the selected set's report is `null`, the screen shall show "This set hasn't been analyzed yet." with a primary "Analyze this set" button.
- [ ] **MAIN-REPLAY-032**: When the player activates "Analyze this set", the screen shall request the analysis, and while it runs the button shall read "Analyzing…" and be disabled.
- [ ] **MAIN-REPLAY-033**: If the analysis request fails, then the screen shall show the failure's message under the button and enable the button again.
- [ ] **MAIN-REPLAY-034**: When the report has no decision points, the screen shall show "No decision points in this set." in place of the filter and the list.
- [ ] **MAIN-REPLAY-035**: While the brain lists no sets, the screen shall show the empty state "No set to analyze yet." with "Play a set against Kumite and its analysis shows up here."
- [ ] **MAIN-REPLAY-036**: While the replay service is offline, the screen shall show the offline banner for the replay service above any report it already holds.
