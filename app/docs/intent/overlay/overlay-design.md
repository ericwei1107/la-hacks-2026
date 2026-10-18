---
parent: high-level-design
prefix: OVERLAY
---

# Overlay

## Context and Design Philosophy

The overlay is an optional layer over Tekken 8 during a set, off by default: the game screen belongs to the game (HLD tenet), and the shell opens the overlay only when `KUMITE_OVERLAY` turns it on. Paper: the Overlay page, "Overlay · In round" and "Overlay · Between rounds", drawn at 1920 × 1080 over a placeholder of the game (the game's own health bars, timer and fighters are placeholders, not overlay content). The overlay draws two things on the night palette and the mat: the corner HUD during a round, and the between-round card after it. Everything else is transparent so the game shows through, and the window passes every click to the game (shell).

The overlay never steals attention mid-round. The HUD is small, quiet and fixed in the top left, under the game's health bar. The card is the only loud moment, and it comes when the round is over.

## Layout

The overlay page is laid out in the 1920 × 1080 design space, and the shell scales the page to the display (shell, overlay window). The HUD's top-left corner sits at (48, 136). The card is centered horizontally, 1000 px wide (`--container-card`), with its bottom 64 px above the bottom edge.

## The live set and the round break

The overlay follows the live set, shows the HUD while a round is live, and shows the card during a round break, all as the HLD defines them. It reads them from the service clients' `useRoundBreak`, the same hook the main window's between-round voice uses, so the two follow the same breaks.

## HUD

Shown while a round is live and the between-round card is not showing. On the night ground at 90%, with a 4 px night-line rule on top:

- The bot character in the display face, and "Level <difficulty>" at the right, from the brain config.
- **Plan**, when the state stream has delivered a `plan` record for the live set: "Plan:" and the plan's `note`, with notation tokens (such as `df+1`) in mono. Hidden otherwise.
- **Habits**, from the analytics service's learning metrics for the live set's last round, refetched each time a round summary arrives: one row per habit with its belt (night variant), its name, its rank name, and its mastery as a whole percent at the right. A habit in the latest round summary's `exploited` list gets a "Bot's target" rust tag and a faint rust row background; a fixed habit gets a "Fixed" outlined tag. Targets come first, then habits by mastery from lowest.
- Before the first round summary of the live set, the habits area reads "Learning your habits. Belts show up after round 1." in night muted.

## Between-round card

The card covers the round-end screen: it shows for exactly as long as a round break is open, for the break's round, n. The round summary and the coach's line for round n come on the coach stream, a separate socket, usually while the card is up and in either order. The card shows the live set's latest summary and coach line for round n whenever they arrived, including just before the break opened. States keep arriving during the round-end screen, still numbered n, so the round stays live and the HUD stays hidden behind the card.

A coach record or round summary never opens the card on its own, and one for any round but n does not show on it.

On the mat ground:

- "Round <n> goes to you" or "Round <n> goes to <bot>", from the round summary for round n. A draw reads "Round <n> is a draw". Until that summary arrives, the line is "Round <n>".
- The coach's text for round n at 30 px bold. Until it arrives, "Coach is reviewing the round…" at the same size in mat muted, so the card does not change height when the line lands.
- At the right, on a 200 px mat-deep panel: the seconds left of a 10-second countdown that starts when the round break opened, in the display face, indigo, over "Round <n + 1>". The countdown holds at 0 when the next round starts late.
- Along the bottom, a 12 px mat-deep bar whose indigo fill shrinks with the seconds left.
- When the break's `round_end` event carried `detail.match_over: true`, the panel reads "Set over" in the display face at 28 px (`--text-xl`), indigo, in place of the seconds and the round label, and the bottom bar is not drawn.

**The card is silent.** The main window speaks the coach's line during the same round break (voice design), so turning the overlay on never adds a second voice. Paper's "Coach speaking" indicator is not drawn: the overlay cannot see the main window's voice player.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| When the HUD shows | While states keep arriving | Always; only on a brain flag | States stop between sets and whenever the brain is not reading a game. Tying the HUD to them keeps the overlay empty when no round is live, including over the desktop during development. |
| When the card shows | While a round break is open | From the coach record's arrival for a fixed 10 seconds | The brain marks both edges of the round-end screen, so the card covers exactly that screen. Keyed to the coach record, the card waits on the replay service before it appears, and a coach record delivered twice (a stream reconnect) restarts it. |
| Countdown | 10 seconds from the `round_end` event, holding at 0 | No number; only "Round <n + 1> next" | Paper draws a number. The round-end screen runs 8 to 10 seconds, so the next round's start usually ends the card before 0, and a hold at 0 covers the rest. |
| Card before the coach line | "Coach is reviewing the round…" in mat muted | Leave the line empty until it lands | The replay service may take up to 8 seconds. An empty card reads as broken on video. |
| Final round label | "Set over" when the `round_end` event's `detail` carries `match_over: true`; "Round <n + 1>" otherwise | Infer the last round from wins and match length | The contracts carry no match length; only the brain knows a set is over, and it marks every `round_end` with `match_over`. The event's `detail` is a free-form object, so the flag fits the existing schema. |
| HUD mastery source | Learning metrics, refetched per round summary | Round summary `top_habits` only | The metrics hold every habit's mastery and fixed flag. Top habits may list only some habits and may omit mastery. |
| Plan row | Shown only when `plan` records arrive | Always shown with a placeholder | The brain does not stream plans yet (HLD open question). An empty row would look broken on video. |

## Open Questions

- **`match_over` reaches main with the brain's M3 merge.** The brain sets it on every `round_end`: true on the round that ends the set (rounds to win reached in versus) and on a stopped session, false otherwise. Brains and recordings from before that merge omit it, and their final card counts down toward a round that never starts.

## References

- Paper file "Kumite — Tatami": Overlay page
- `../shell/shell-design.md` (overlay window)
- `../service-clients/service-clients-design.md` (streams, plan slot, `useRoundBreak`)
- `../voice/voice-design.md` (the between-round voice)
