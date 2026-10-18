# Stats screen specs

Design: `stats-design.md`

## Headline numbers

- [ ] **MAIN-STATS-001**: The Stats screen shall show the selected set's total low block rate as its headline, labelled "Low block rate".
- [ ] **MAIN-STATS-002**: When the trends hold a set before the selected one, the headline shall add the change in low block rate as "Down <n> from last set", "Up <n> from last set" or "Same as last set", in whole percentage points.
- [ ] **MAIN-STATS-003**: When `low_defense` appears in the `exploited` list of the selected set's last round summary, the headline shall add "This is the habit <bot character> is hunting."
- [ ] **MAIN-STATS-004**: The Stats screen shall show punish rate and counter hits given, each with its signed change since the previous set as "+<n> vs last set" when the trends hold one.
- [ ] **MAIN-STATS-005**: The Stats screen shall show throw break rate with "<k> of <n> broken", where k is the human's throw-break events and n is k plus the throw events targeting the human in the set's recording.
- [ ] **MAIN-STATS-006**: The Stats screen shall show counter hits taken with "<total over round count> per round".
- [ ] **MAIN-STATS-007**: The Stats screen shall treat the trend point immediately before the selected set's point, by start time, as "last set".
- [ ] **MAIN-STATS-008**: When a rate is null, the Stats screen shall show an em dash with "Didn't come up this set".

## Damage taken by situation

- [ ] **MAIN-STATS-010**: The Stats screen shall show one bar per situation in the set's damage taken by situation, largest first, each bar's length proportional to the largest, with the total labelled "<total> total".
- [ ] **MAIN-STATS-011**: The Stats screen shall draw a situation's bar in `--color-bot` with a bold label when that situation appears in the `exploited` list of the set's last round summary.
- [ ] **MAIN-STATS-012**: When an exploited situation took damage, the Stats screen shall show "Fix the <situation> habit and you cut <share> of the damage you take." for the exploited situation with the most damage.

## Across sessions

- [ ] **MAIN-STATS-020**: The Stats screen shall frame in `--color-primary` a bar chart titled "Across sessions" of one stat over up to five of the player's sets ending with the selected one, from the trends for the set's player and human character.
- [ ] **MAIN-STATS-021**: The across-sessions chart shall offer a select of Low block rate, Punish rate, Throw break rate, Counter hits taken and Counter hits given, starting on Low block rate.
- [ ] **MAIN-STATS-022**: The across-sessions chart shall label each bar with its value above and its time and day below, and draw the selected set's bar in `--color-primary` and the others in muted ink.

## States

- [ ] **MAIN-STATS-030**: While the stats are loading for the first time, the Stats screen shall show skeleton headline numbers and bars.
- [ ] **MAIN-STATS-031**: While the brain lists no sets, the Stats screen shall show the empty state "No stats yet." with "Play a set against Kumite and its numbers show up here."
- [ ] **MAIN-STATS-032**: While analytics is offline, the Stats screen shall show the offline banner for analytics above any stats it already holds.

## Implemented in

| Spec IDs | Entry point |
|---|---|
| MAIN-STATS-001 – MAIN-STATS-032 | `src/renderer/src/main-window/screens/Stats.tsx` (`Stats`, `StatsBody`, `Headline`, `DamageBySituation`, `AcrossSessions`) |
