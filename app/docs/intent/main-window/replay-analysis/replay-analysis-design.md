---
parent: main-window
prefix: MAIN-REPLAY
---

# Replay analysis screen

## Context and Design Philosophy

The Replay analysis screen answers "what was the best option at every moment that mattered, and why?". It shows the replay service's report for the selected set. Paper: the Replay analysis artboard. The indigo frame holds the top habit and its smallest fix, because that is the one thing to take into the next set.

## Top habit

The report's first habit, framed in indigo:

- **The move to make**, at the left: when the best option of the habit's first decision point has a command that starts with a direction, a 3 × 3 direction pad with that direction's cell filled indigo and an arrow. Under it, "hold <command>" when the command is a direction alone ("hold d/b"), or "press <command>" when it includes buttons.
- "Your top habit, and the smallest fix for it", muted, over the habit's `min_change` in the display face, in indigo.
- A sentence built from the habit: "You did this in <p>% of these spots, <count> times this set."
- At the right, past a hairline: the damage lost to the habit, the sum of `cost` over the decision points whose frame is one of the habit's `moments`, labelled "damage lost to this habit".

## Situation filter

Chips: "All" with the count of decision points, then one chip per distinct decision-point `situation`, in order of first appearance, each with its count. The selected chip fills indigo. Selecting a chip shows only that situation's decision points.

## Decision points

The filtered decision points, in report order. The first is expanded; the rest are collapsed rows. Clicking a row expands it and collapses the one that was open.

- **Expanded:** "Round <r>, frame <f>" over the situation in words; the damage at the right ("24 damage"). Below, three columns: "You did" with the actual option, and "Best option" with the best option and its command in indigo; the options as meters, best first and in indigo, the others muted, each with its percentage, and "your pick" beside the actual option; and "Why" with the explanation.
- **Collapsed:** "Round <r>, frame <f>", the situation, a short line, the signed cost, and a chevron. The short line is "<Actual>. Best: <best>" for a point the player got wrong, and a check with "<Actual>. Right call" in green for a point marked `good`. Cost is "−<cost>" for a wrong call and "+<cost>" in green for a good one.
- The list shows four points at first, and "Show <n> more in this situation" reveals the rest.

When the screen opens with a focus (round and frame), it selects "All", expands the decision point at that round and frame if there is one, and shows the full list.

## Option words

An option's name is shown in words (design-system). Its command is shown in notation after the name in parentheses ("Block low (d/b)"). The actual option's command comes from the option of the same name in the point's option list, when there is one.

## States

- **Loading:** skeleton top habit and rows.
- **Not analyzed** (the report is `null`): the empty-state pattern with "This set hasn't been analyzed yet." / "Kumite's replay service scores every decision you made. It takes a minute or two." and a primary "Analyze this set" button. While the analysis runs, the button reads "Analyzing…" and is disabled. When it fails, a muted line under the button says why.
- **No decision points** in the report: the top habit (if any) and the line "No decision points in this set."
- **No sets:** the empty state "No set to analyze yet." / "Play a set against Kumite and its analysis shows up here."
- **Offline:** the offline banner for the replay service.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Situation chips | One per distinct `situation` string | Grouping by a situation class parsed out of the sentence | The report's `situation` is free text. Grouping by exact text is arithmetic; parsing classes out of prose is guesswork that belongs to the replay service. |
| The habit sentence | A fixed template over `p` and `count` | The Paper copy "You pressed a button in 5 of 6 of these spots…" | That sentence needs facts the report does not carry. A template over contract fields is what the HLD tenet allows. |
| Damage lost to the habit | Sum of `cost` over decision points at the habit's `moments` | A field from the replay service | The report carries both; summing them is arithmetic. |

## Open Questions & Future Decisions

### Deferred
1. Moments are frame numbers without rounds, and frames restart each round. A decision point in another round at the same frame would be counted toward the habit too. Ask Garrett for `{round, frame}` moments.
2. Decision-point situations that share a class ("after blocking df+1 at close range", "after blocking df+1 near the wall") form separate chips. A `situation_class` field from the replay service would let the chips group them as Paper shows.

## References

- Paper file "Kumite — Tatami": Replay analysis
- `../../../../../contracts/report.schema.json`
