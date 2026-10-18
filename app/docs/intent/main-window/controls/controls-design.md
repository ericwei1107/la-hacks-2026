---
parent: main-window
prefix: MAIN-CONTROLS
---

# Controls screen

## Context and Design Philosophy

The Controls screen sets up the next set: how hard the bot plays and who is playing. Paper: the Controls artboard. Everything on it reads and writes the brain's config, and shows what the brain confirms, so the screen never claims a setting the bot is not using.

## Difficulty

Five preset cards: 1 Rookie, 2 Novice, 3 Intermediate, 4 Advanced, 5 Tekken God. The config's `difficulty` card fills indigo. Choosing a preset saves the difficulty together with the preset's three knob values, so the sliders below show the preset:

| Preset | Reaction delay | Punish accuracy | Exploit weight |
|---|---|---|---|
| 1 Rookie | 30 frames | 40% | 20% |
| 2 Novice | 24 frames | 60% | 40% |
| 3 Intermediate | 18 frames | 80% | 60% |
| 4 Advanced | 12 frames | 92% | 80% |
| 5 Tekken God | 6 frames | 100% | 100% |

These are the design doc's difficulty presets (design doc section 4).

Three sliders fine-tune the knobs, each showing its current value at the right of its label:

- **Reaction delay**, 30 frames ("slow") at the left to 6 frames ("fast") at the right, in whole frames, shown in mono ("14 frames").
- **Punish accuracy**, 0 to 100%, "Misses most punishes" to "Punishes everything".
- **Exploit weight**, 0 to 100%, "Plays honest" to "Hunts your habits".

A slider shows the config's knob, or the selected preset's value when the config has none. Dragging moves it freely; letting go, or a keyboard step, saves that one knob, keeping the others.

## Match

- **Bot character:** a select of Kazuya, Devil Jin, King and Shaheen, saved on change.
- **Player name:** a text field saved on Enter or when it loses focus, if changed and not empty.
- **Demo mode:** a toggle, "Same seed and habits every run, for the booth".
- **Coach voice:** a toggle, "Speaks between rounds and in the Coach tab".
- **Push-to-talk key:** the key as a key cap with a "Change" link. Change waits for the next key press and stores it on this machine. Escape cancels. The key is a local setting, not part of the brain config.

## Saving

Every change is sent to the brain as a partial config. Until the brain answers, the changed control shows the new value. When the brain answers, the screen shows the merged config it returned. If the save fails, the control returns to the brain's last confirmed value and a muted line under the section says "Couldn't save. <reason>".

## States

- **Loading:** skeleton cards and sliders.
- **Offline:** the offline banner for the brain; the controls show the last confirmed config and are disabled.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| What a preset saves | Difficulty plus its three knob values | Difficulty alone, clearing knobs | The config contract lets knobs override the preset, and a partial update cannot clear a knob. Sending the preset's values makes the sliders and the bot agree. |
| When a slider saves | On release or a keyboard step | On every movement | One save per decision keeps the brain from replanning on each pixel of a drag. |
| Push-to-talk key storage | On this machine | In the brain config | The config contract has no field for it, and the key belongs to the keyboard at this machine. |

## References

- Paper file "Kumite — Tatami": Controls
- `../../../../../contracts/config.schema.json`
- `../../../../../prep/design-doc.md` section 4 (difficulty presets; local only)
