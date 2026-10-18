# Focus card specs

Design: `focus-design.md`

## Source

- [ ] **MAIN-FOCUS-001**: While `KUMITE_INSIGHTS` is not `1` in the process environment or `app/.env`, the Stats screen shall not request insights or show the focus card, evidence or moments.
- [ ] **MAIN-FOCUS-002**: While `KUMITE_INSIGHTS` is `1`, the Stats screen shall request `GET /insights/<selected set id>?limit=3` from the analytics service and show the focus card above the headline numbers.
- [ ] **MAIN-FOCUS-003**: If an insights reply's `session_id` is not the selected set's id, then the focus card shall not use it.

## The card

- [ ] **MAIN-FOCUS-010**: The focus card shall show the heading "What to practice", adding "Selected focus" when `focus.mode` is `manual`.
- [ ] **MAIN-FOCUS-011**: When `focus.metric` is set, the focus card shall show that metric's label and its fraction as "<successes> of <opportunities> lows blocked", "<successes> of <opportunities> throws broken" or "<successes> of <opportunities> punishes landed" for low defense, throw defense and punish conversion.
- [ ] **MAIN-FOCUS-012**: When a shown metric's `value` is a number, the focus card shall show it as a whole percentage beside its fraction, and when `value` is null it shall show no percentage.
- [ ] **MAIN-FOCUS-013**: The focus card shall label punish conversion "Estimated" wherever it shows it.
- [ ] **MAIN-FOCUS-014**: When `focus.metric` is set, the focus card shall show `focus.reason` in muted text.
- [ ] **MAIN-FOCUS-015**: When `focus.action_reviewed` is true, the focus card shall show `focus.action`; otherwise it shall show "Review these moments" in its place.
- [ ] **MAIN-FOCUS-016**: When `focus.metric` is null, the focus card shall show `focus.reason` as its main line.
- [ ] **MAIN-FOCUS-017**: The focus card shall show one row per metric with, by state: observed, its fraction and percentage; early signal, "<opportunities> <noun> seen; need <threshold> for an automatic focus" when the reply gives a threshold, or "<opportunities> <noun> seen; more needed for an automatic focus" when it does not; no opportunities, "No opportunities observed" and "—"; invalid, "Data needs review" with no rate.
- [ ] **MAIN-FOCUS-018**: While `quality` is `invalid`, the focus card shall show "This set's data needs review before it can suggest a focus." and no focus, action or metric rate.
- [ ] **MAIN-FOCUS-019**: When `synthetic` is true, the focus card shall show a persistent "Synthetic example" tag, and when `synthetic` is null, "Source type unknown".

## Evidence and moments

- [ ] **MAIN-FOCUS-020**: The Stats screen shall show under the focus card the evidence rows of the focus metric, or with no focus metric those of the metric with the most opportunities, with "Showing <n> of <evidence_total>".
- [ ] **MAIN-FOCUS-021**: The Stats screen shall show under the evidence the reply's moments in order, with "Showing <n> of <moments_total>".
- [ ] **MAIN-FOCUS-022**: Each evidence or moment row shall read "Round <r>, frame <f>: <event>", with "frame —" when the frame is null, where the event names the hit level, the kind, the damage when above zero, and the frame advantage on a block.
- [ ] **MAIN-FOCUS-023**: Each evidence or moment row shall show its outcome as a word as well as a mark.
- [ ] **MAIN-FOCUS-024**: A mixed moment shall show each entry of its `metric_outcomes` with its own outcome word.
- [ ] **MAIN-FOCUS-025**: Each evidence or moment row shall be a button that expands in place, on click, Enter or Space, to show the event's fields and the response location when present, with `aria-expanded` reflecting its state.
- [ ] **MAIN-FOCUS-026**: The Stats screen shall keep an expanded row while its set stays selected and its line appears in the latest reply, and collapse it when the set changes or the line no longer appears.

## Freshness

- [ ] **MAIN-FOCUS-030**: The Stats screen shall refetch insights on each trigger on which the frame refetches the selected set's stats and learning metrics.
- [ ] **MAIN-FOCUS-031**: The focus card shall show "Through completed round <n>" from `freshness.latest_completed_round`, or "No completed rounds yet" when it is null.
- [ ] **MAIN-FOCUS-032**: While `freshness.pending_learning_rounds` is non-empty, the focus card shall show "Round <n> learning is still being saved." for its first entry and keep the metric counts shown.
- [ ] **MAIN-FOCUS-033**: While `freshness.learning_ahead_rounds` is non-empty, the focus card shall show "Learning is ahead of the recording; waiting for it to catch up."
- [ ] **MAIN-FOCUS-034**: If an insights request fails after a good reply for the selected set, then the focus card shall keep that reply's view labelled "Not up to date" until the next trigger succeeds.
- [ ] **MAIN-FOCUS-035**: Before any good reply for the selected set, the focus card shall show skeleton lines while the request is pending.
- [ ] **MAIN-FOCUS-036**: If an insights request fails before any good reply for the selected set, then the focus card shall show "Insights come back when analytics reconnects." when analytics is offline, "Analytics has no insights for this set yet." for a 404, and "Insights aren't available for this set right now." otherwise.

## Implemented in

| Spec IDs | Entry point |
|---|---|
| MAIN-FOCUS-001 – MAIN-FOCUS-003 | `src/renderer/src/main-window/screens/Stats.tsx` (`Stats`), `src/renderer/src/main-window/focus/Focus.tsx` (`Focus`) |
| MAIN-FOCUS-010 – MAIN-FOCUS-019, MAIN-FOCUS-031 – MAIN-FOCUS-036 | `src/renderer/src/main-window/focus/Focus.tsx` (`FocusCard`, `MetricRow`, `Focus`), wording in `focus/words.ts` |
| MAIN-FOCUS-020 – MAIN-FOCUS-026 | `src/renderer/src/main-window/focus/Focus.tsx` (`Lists`, `EventRow`, `Detail`), wording in `focus/words.ts` |
| MAIN-FOCUS-030 | `src/renderer/src/main-window/frame.tsx` (`FrameProvider`) |
