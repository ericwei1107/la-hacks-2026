# Sessions screen specs

Design: `sessions-design.md`

## Set list

- [ ] **MAIN-SESSIONS-001**: The Sessions screen shall list one card per set from the brain's set list, newest first.
- [ ] **MAIN-SESSIONS-002**: Each set card shall show the set's start time, "<human character> vs <bot character>", and "Level <difficulty> · <round count> rounds · <duration>", writing "round" when the count is one.
- [ ] **MAIN-SESSIONS-003**: When a set has no `ended_at`, its card shall show "in progress" in place of the duration.
- [ ] **MAIN-SESSIONS-004**: Each set card shall show the score as the count of rounds the human won, an en dash, and the count of rounds the bot won, labelled "Win" in `--color-primary` when the human won more, "Loss" in muted ink when the bot won more, and "Draw" otherwise.
- [ ] **MAIN-SESSIONS-005**: The Sessions screen shall frame the selected set's card in `--color-primary` on `--color-surface`.
- [ ] **MAIN-SESSIONS-006**: When the player clicks a set card, the Sessions screen shall make that set the selected set.

## Set detail

- [ ] **MAIN-SESSIONS-010**: The set detail shall show the start time and level ("Today at 2:41 PM, level 3") over the result in the display face ("Loss 1–2 to Kazuya", "Win 2–1 over Kazuya").
- [ ] **MAIN-SESSIONS-011**: When the player activates the set detail's "Replay analysis" button, the main window shall open the Replay analysis screen on that set.
- [ ] **MAIN-SESSIONS-012**: The set detail shall show one timeline row per round, labelled with the round number and "You win", "<bot character> wins", or "Draw" when the round has no winner.
- [ ] **MAIN-SESSIONS-013**: Each timeline row shall draw the human's events above a line in `--color-primary` and the bot's events below it in `--color-text-muted`, placed by frame on a scale shared by all rounds of the set.
- [ ] **MAIN-SESSIONS-014**: The timeline shall draw hit and counter-hit events as dots, block events as squares, throw and throw-break events as diamonds, and knockdown events as triangles, and shall not draw other event kinds.
- [ ] **MAIN-SESSIONS-015**: The timeline shall draw a bot event in `--color-bot` when its `situation` appears in the `exploited` list of the same round's summary.
- [ ] **MAIN-SESSIONS-016**: The set detail shall show damage dealt as the sum of the round summaries' `bot_damage_taken`, damage taken as the sum of their `human_damage_taken`, knockdowns as the human's knockdown events, an en dash, and the bot's, and throws broken as the human's throw-break events "of" the throw events targeting the human, every attempt counted once whether broken or not, or an em dash when no throw targeted the human.
- [ ] **MAIN-SESSIONS-017**: The Sessions screen shall read the selected set's recording without per-frame states.
- [ ] **MAIN-SESSIONS-018**: If the selected set's recording cannot be loaded, then the set detail shall show "This set's recording isn't available." in place of the timeline and totals.

## States

- [ ] **MAIN-SESSIONS-020**: While the set list is loading for the first time, the Sessions screen shall show a skeleton list and a skeleton detail panel.
- [ ] **MAIN-SESSIONS-021**: While the brain's set list is loaded and empty, the Sessions screen shall show the empty state "The mat is empty." with "Play a set against Kumite and it shows up here."
- [ ] **MAIN-SESSIONS-022**: While the Sessions empty state shows and the brain is online, its status line shall read "The brain is connected and waiting for round 1." with a green dot.
- [ ] **MAIN-SESSIONS-023**: While the brain is offline, the Sessions screen shall show the offline banner for the brain above any sets it already holds.

## Implemented in

All paths are under `src/renderer/src/main-window/`.

| Spec IDs | Entry point |
|---|---|
| MAIN-SESSIONS-001 – MAIN-SESSIONS-023 | `screens/Sessions.tsx` (`Sessions`, `SetCard`, `SetDetail`, `Timeline`, `Totals`) |
| MAIN-SESSIONS-004, MAIN-SESSIONS-016 | `setData.ts` (`roundScore`, `throwCounts`) |
