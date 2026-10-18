---
parent: main-window
prefix: MAIN-STATS
---

# Stats screen

## Context and Design Philosophy

The Stats screen gives the per-set numbers and how they move across sets. Paper: the Stats artboard. The low-block rate leads because it is the habit the demo bot hunts. The indigo frame holds the across-sessions chart, because change over time is what the player is after.

Its data is the analytics service's stats for the selected set and the player's trends for the set's human character, plus the set's recording for throw counts and the bot's target.

## Headline numbers

- **Low block rate**, large: the set's total `low_block_rate`. The line under it: the change since the previous set in the trends ("Down 4 from last set", "Up 3 from last set", "Same as last set"), then "This is the habit <bot> is hunting." when `low_defense` is in the last round summary's `exploited`.
- **Punish rate**, with "+n vs last set".
- **Throw break rate**, with "<k> of <n> broken" from the recording's throw-break and throw events, as in the Sessions totals: n counts each throw attempt at the human once, so the note agrees with the service's rate.
- **Counter hits taken**, with "<x> per round" (total over the round count, one decimal when not whole).
- **Counter hits given**, with "+n vs last set".

"Last set" is the trend point just before the selected set's own point, by start time. When there is none, the change line is left out.

## Damage taken by situation

The set's `damage_taken_by_situation`, one bar per situation, largest first, each bar's length relative to the largest, with the total at the top right ("351 total"). A situation the bot is exploiting (in the last round summary's `exploited`) is drawn rust with a bold label.

Under the bars, when an exploited situation took damage: "Fix the <situation> habit and you cut <share> of the damage you take." The share is that situation's damage over the total, written as a share (design-system).

## Across sessions

A bar chart of one stat over the player's last five sets up to and including the selected one, from the trends. A select chooses the stat: Low block rate, Punish rate, Throw break rate, Counter hits taken, Counter hits given. Each bar is labelled with its value and, below the axis, its time in mono and its day ("Today", "Oct 16"). The selected set's bar is indigo, the others muted.

## States

- **Loading:** skeleton headline and bars.
- **No sets:** the empty state "No stats yet." / "Play a set against Kumite and its numbers show up here."
- **Offline:** the offline banner for analytics.
- A rate that is null (the situation never happened) reads as an em dash with "Didn't come up this set".

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Headline stat | Always low block rate | The stat of whichever habit the bot targets | Paper fixes the layout around low block rate, and the hunted-habit line says when it is the target. A moving headline would reshuffle the screen between sets. |
| "vs last set" | Difference from the previous trend point | A field from analytics | Trends carry every set's values; subtracting two is arithmetic. |
| Throw counts | From the recording's events | Deriving them from the rate | A rate cannot give "1 of 3"; the events can. |

## References

- Paper file "Kumite — Tatami": Stats
- `../../../../../contracts/api.md` (analytics `/stats` and `/trends`)
