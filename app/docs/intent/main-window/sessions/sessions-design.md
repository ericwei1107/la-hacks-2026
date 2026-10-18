---
parent: main-window
prefix: MAIN-SESSIONS
---

# Sessions screen

## Context and Design Philosophy

The Sessions screen answers "what sets have I played, and how did this one go?". Paper: the Sessions artboard, and Sessions · Empty on the States page. A list of sets sits on the left; the open set's detail, framed in indigo, sits on the right.

## Set list

One card per set the brain lists, newest first:

- Start time ("Today, 2:41 PM"), muted.
- "<Human character> vs <Bot character>", bold.
- "Level <difficulty> · <n> rounds · <duration>", muted. Duration is `ended_at` minus `started_at`; a set with no `ended_at` reads "in progress" instead.
- At the right: "Win" in indigo or "Loss" in muted, over the score. The score counts round winners: the human's wins, an en dash, the bot's wins, so "1–2". A set whose rounds are tied reads "Draw".

The open set's card is framed in indigo on mat light; the others have hairline borders. The open set is the selected set (main-window); clicking a card selects it.

## Set detail

- "Today at 2:41 PM, level 3" over the result in the display face: "Loss 1–2 to Kazuya" or "Win 2–1 over Kazuya".
- A primary "Replay analysis" button that opens Replay analysis on this set.
- A legend: hit (dot), block (square), throw (diamond), knockdown (triangle), and, at the right, rust for "Bot's planned exploit".
- **Timeline.** One row per round, labelled "R1" and who won ("You win" in indigo, "<Bot> wins" muted). A line runs the length of the round. The human's events sit above it in indigo and the bot's below in muted ink, each at its frame along the line. Rounds are drawn to one scale, so a shorter round has a shorter line. A bot event is rust when its `situation` is one the round's summary lists in `exploited`. Events of kinds other than hit, counter hit, block, throw, throw break and knockdown are not drawn.
- **Totals** across the set's round summaries: damage dealt (the sum of `bot_damage_taken`), damage taken (the sum of `human_damage_taken`), knockdowns as "<human's>–<bot's>" (knockdown events by actor), and throws broken as "<k> of <n>": the human's throw-break events out of every throw aimed at the human. The brain emits a `throw` event for every throw attempt, broken or not, and a `throw_break` event besides when the human escapes, so n is the throw events targeting the human; adding the breaks again would count escaped throws twice. With no throws aimed at the human, the total reads as an em dash rather than "0 of 0".

The timeline and totals come from the set's recording, read without per-frame states.

## States

- **Loading:** a skeleton list and a skeleton detail panel.
- **Empty** (the brain lists no sets): the empty state "The mat is empty." / "Play a set against Kumite and it shows up here." with a status line: green "The brain is connected and waiting for round 1." while the brain is online, or an outlined dot and "The brain is offline. Start it and your sets show up here." otherwise.
- **Offline:** the offline banner for the brain over whatever list the screen already holds.
- **Recording unavailable:** the detail keeps its header and button and replaces the timeline and totals with a muted line, "This set's recording isn't available."

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Where the score comes from | Counting round winners in the set metadata | The `result` string in the set metadata | `result` is free text and may be empty while a set runs; the round winners are structured and always present. |
| Event actor | Above the line: events whose `actor` is the human's slot | Events whose `target` is the human | The Paper caption reads "Above the line: you"; the actor is who did the thing. |
| Timeline scale | One scale for all rounds, from the longest round | Each round stretched to full width | A shared scale shows which rounds ended early, which the design's differing line lengths show. |

## Open Questions & Future Decisions

### Deferred
1. The event contract does not say which slot is the `actor` of a `block` or `throw_break`. The screen takes the actor to be the player who performed the action (the blocker, the breaker), matching the brain and the analytics service.

## References

- Paper file "Kumite — Tatami": Sessions; States, Sessions · Empty
- `../main-window-design.md`
