---
parent: high-level-design
prefix: OVERLAY
---

# Overlay

## Context and Design Philosophy

The overlay is what the player sees over Tekken 8 during a set. Paper: the Overlay page, "Overlay · In round" and "Overlay · Between rounds", drawn at 1920 × 1080 over a placeholder of the game (the game's own health bars, timer and fighters are placeholders, not overlay content). The overlay draws two things on the night palette and the mat: the corner HUD during a round, and the between-round card after it. Everything else is transparent so the game shows through, and the window passes every click to the game (shell).

The overlay never steals attention mid-round. The HUD is small, quiet and fixed in the top left, under the game's health bar. The card is the only loud moment, and it comes when the round is over.

## Layout

The overlay page is laid out in the 1920 × 1080 design space, and the shell scales the page to the display (shell, overlay window). The HUD's top-left corner sits at (48, 136). The card is centered horizontally, 1000 px wide (`--container-card`), with its bottom 64 px above the bottom edge.

## The live set

The overlay follows the set being played: the `session_id` of the latest `state` record on the brain's state stream. A **round is live** while state records keep arriving, with the latest received less than 2 seconds ago.

## HUD

Shown while a round is live and the between-round card is not showing. On the night ground at 90%, with a 4 px night-line rule on top:

- The bot character in the display face, and "Level <difficulty>" at the right, from the brain config.
- **Plan**, when the state stream has delivered a `plan` record for the live set: "Plan:" and the plan's `note`, with notation tokens (such as `df+1`) in mono. Hidden otherwise.
- **Habits**, from the analytics service's learning metrics for the live set's last round, refetched each time a round summary arrives: one row per habit with its belt (night variant), its name, its rank name, and its mastery as a whole percent at the right. A habit in the latest round summary's `exploited` list gets a "Bot's target" rust tag and a faint rust row background; a fixed habit gets a "Fixed" outlined tag. Targets come first, then habits by mastery from lowest.
- Before the first round summary of the live set, the habits area reads "Learning your habits. Belts show up after round 1." in night muted.

## Between-round card

Shown when a `coach` record for the live set arrives on the coach stream, for 10 seconds, or until a `state` record arrives for a later round than the coach record's, whichever comes first. On the mat ground:

- "Round <n> goes to you" or "Round <n> goes to <bot>", from the round summary for the same round. A draw reads "Round <n> is a draw". Without a matching summary, the line is "Round <n>".
- The coach's text at 30 px bold.
- At the right, on a 200 px mat-deep panel: the seconds left in the display face, indigo, over "Round <n + 1>".
- Along the bottom, a 12 px mat-deep bar whose indigo fill shrinks with the seconds left.

The "Coach speaking" line from Paper belongs to the voice update.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| When the HUD shows | While states keep arriving | Always; only on a brain flag | States stop between rounds and between sets. Tying the HUD to them keeps the overlay empty when no round is live, including over the desktop during development. |
| Card duration | 10 seconds | Until the next round's first state only | The round-end screen gives 8 to 10 seconds. A fixed countdown is what Paper draws; the next round's first state still ends it early. |
| HUD mastery source | Learning metrics, refetched per round summary | Round summary `top_habits` only | The metrics hold every habit's mastery and fixed flag. Top habits may list only some habits and may omit mastery. |
| Plan row | Shown only when `plan` records arrive | Always shown with a placeholder | The brain does not stream plans yet (HLD open question). An empty row would look broken on video. |

## References

- Paper file "Kumite — Tatami": Overlay page
- `../shell/shell-design.md` (overlay window)
- `../service-clients/service-clients-design.md` (streams, plan slot)
