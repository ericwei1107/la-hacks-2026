# Coach screen specs

Design: `coach-design.md`

## Conversation

- [ ] **MAIN-COACH-001**: The Coach screen shall keep one conversation per set for as long as the app runs, and show the selected set's conversation.
- [ ] **MAIN-COACH-002**: The Coach screen shall show the player's messages right-aligned in `--color-primary` bubbles and the coach's answers left-aligned as text under a "Coach" label.
- [ ] **MAIN-COACH-003**: When the player sends a question, the Coach screen shall call `/coach/chat` with the selected set's id, the player's name, the question, and the earlier messages as history entries with role `user` or `coach`.
- [ ] **MAIN-COACH-004**: The Coach screen shall take the player's name from the brain config, and from the selected set's `player` when the config is unavailable.
- [ ] **MAIN-COACH-005**: While an answer is pending, the Coach screen shall show "Coach" with "Thinking…" in its place and disable the input.
- [ ] **MAIN-COACH-006**: The Coach screen shall show each citation of an answer as a chip reading "Round <r>, frame <f>" with a play mark.
- [ ] **MAIN-COACH-007**: When the player activates a citation chip, the main window shall open Replay analysis on the selected set focused at that round and frame.
- [ ] **MAIN-COACH-008**: If a question fails, then the Coach screen shall show "Couldn't reach the coach." with the failure's message in place of the answer.
- [ ] **MAIN-COACH-009**: While the selected set's conversation is empty, the Coach screen shall show "Ask about this set. Try: Why did I lose round 2?" in muted text.

## Input bar

- [ ] **MAIN-COACH-010**: The Coach screen shall show a disabled "Hold to talk" button with the push-to-talk key as a key cap, explaining on hover that voice comes with the voice update.
- [ ] **MAIN-COACH-011**: When the player presses Enter in the question field or activates the send arrow with a non-empty question, the Coach screen shall send the question and clear the field.
- [ ] **MAIN-COACH-012**: The Coach screen shall show a "Coach voice" toggle bound to the brain config's `voice` and save a change to the brain config.

## States

- [ ] **MAIN-COACH-020**: While the brain lists no sets, the Coach screen shall show the empty state "No set to talk about yet." with "Play a set against Kumite, then ask the coach about it."
- [ ] **MAIN-COACH-021**: While the replay service is offline, the Coach screen shall show the offline banner for the replay service and disable the question field and send arrow.

## Implemented in

| Spec IDs | Entry point |
|---|---|
| MAIN-COACH-001 – MAIN-COACH-021 | `src/renderer/src/main-window/screens/Coach.tsx` (`Coach`, `Conversation`) |
| MAIN-COACH-010 | `src/renderer/src/main-window/pushToTalk.ts` (`usePushToTalkKey`) |
