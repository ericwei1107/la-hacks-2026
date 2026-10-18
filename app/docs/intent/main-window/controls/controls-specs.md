# Controls screen specs

Design: `controls-design.md`

## Difficulty

- [ ] **MAIN-CONTROLS-001**: The Controls screen shall show five preset cards, 1 Rookie, 2 Novice, 3 Intermediate, 4 Advanced and 5 Tekken God, filling the card of the config's `difficulty` with `--color-primary`.
- [ ] **MAIN-CONTROLS-002**: When the player chooses a preset, the Controls screen shall save that difficulty with the preset's reaction delay, punish accuracy and exploit weight: 30, 0.40, 0.20; 24, 0.60, 0.40; 18, 0.80, 0.60; 12, 0.92, 0.80; 6, 1.00, 1.00 for presets 1 to 5.
- [ ] **MAIN-CONTROLS-003**: The Controls screen shall show sliders for reaction delay (30 frames at the left to 6 at the right, whole frames), punish accuracy (0 to 100%) and exploit weight (0 to 100%), each with its current value beside its label.
- [ ] **MAIN-CONTROLS-004**: Each slider shall show the config's knob value, or the selected preset's value when the config has no such knob.
- [ ] **MAIN-CONTROLS-005**: When the player releases a slider or moves it with the keyboard, the Controls screen shall save that knob and keep the config's other knobs.

## Match

- [ ] **MAIN-CONTROLS-010**: The Controls screen shall show a bot character select of Kazuya, Devil Jin, King and Shaheen, and save the choice on change.
- [ ] **MAIN-CONTROLS-011**: When the player presses Enter in the player name field or the field loses focus with a changed, non-empty name, the Controls screen shall save the name.
- [ ] **MAIN-CONTROLS-012**: The Controls screen shall show "Demo mode" and "Coach voice" toggles bound to the config's `demo_mode` and `voice`, and save a change on toggle.
- [ ] **MAIN-CONTROLS-013**: The Controls screen shall show the push-to-talk key as a key cap with a "Change" link.
- [ ] **MAIN-CONTROLS-014**: When the player activates "Change", the Controls screen shall store the next key pressed as the push-to-talk key on this machine, or keep the current key if that press is Escape.

## Saving

- [ ] **MAIN-CONTROLS-020**: The Controls screen shall send every change to the brain as a partial config containing only the changed fields.
- [ ] **MAIN-CONTROLS-021**: While a save is pending, the changed control shall show its new value.
- [ ] **MAIN-CONTROLS-022**: When a save succeeds, the Controls screen shall show the merged config the brain returned.
- [ ] **MAIN-CONTROLS-023**: If a save fails, then the changed control shall return to the brain's last confirmed value and the section shall show "Couldn't save." with the failure's message.

## States

- [ ] **MAIN-CONTROLS-030**: While the config is loading for the first time, the Controls screen shall show skeleton cards and sliders.
- [ ] **MAIN-CONTROLS-031**: While the brain is offline, the Controls screen shall show the offline banner for the brain and disable every control except the push-to-talk key.

## Implemented in

| Spec IDs | Entry point |
|---|---|
| MAIN-CONTROLS-001 – MAIN-CONTROLS-031 | `src/renderer/src/main-window/screens/Controls.tsx` (`Controls`, `KnobSlider`) |
| MAIN-CONTROLS-013, MAIN-CONTROLS-014 | `src/renderer/src/main-window/pushToTalk.ts` |
