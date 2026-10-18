# Chloe: focus and insights examples for review

This completes Eric's example handoff prerequisite for the original optional C3, called C4–C7 in the revised parallel plan. The [generated fixture index](../fixtures/insights/README.md) supplies eleven real-builder snapshots. The [proposal](../INSIGHTS_PROPOSAL.md) supplies field definitions and a TypeScript sketch. These files are review material; live route/consumer agreement is still pending.

## Display rules

| Field or state | Render | Avoid |
| --- | --- | --- |
| `metrics.*.successes/opportunities` | Supplied fraction for the completed-round population, e.g. “0 of 16 lows blocked” | Recomputing counts from the sampled evidence or moment list |
| `observed` | Fraction and optional percentage when value is numeric | Treating five observations as statistical confidence or a causal finding |
| `early_signal` | “3 lows seen; need 5 for an automatic focus” plus the observed fraction | Hiding a usable early count or suggesting automatic focus before the threshold |
| `no_opportunities` | “No opportunities observed” and “—” for rate | Rendering null as 0% or implying no mistakes occurred |
| Metric `invalid` | “Data needs review”; hide its rate and advice; retain diagnostic counts in a review view | Dividing, clamping or presenting an orphan 1/0 break count as a valid percentage |
| `quality.state=invalid` | Suppress coaching recommendations and show a source-data problem | Continuing to display stale advice as current |
| `focus.metric=null` | Use the supplied reason, e.g. “More observations needed” | Selecting another focus in TypeScript |
| `focus.mode=manual` | “Selected focus”, with the metric's own state/fraction | Presenting a three-observation manual selection as automatic |
| `focus.action_status=draft_awaiting_Garrett_review` | Neutral “Review these moments”; action prose is review-only | Showing unapproved mechanics as production advice |
| `estimated=true` | “Estimated punish conversion”; retain provisional timing caveat | Claiming a mechanically guaranteed punish or enabling punish focus |
| `freshness.completed_rounds` | “Through completed round N”, using the largest completed round or “No completed rounds yet” | Using a newer active `latest_recording_round` as completed learning |
| `pending_learning_rounds` | “Learning for round 2 is still being saved” while defense counts remain valid | Replacing missing learning with zero or discarding valid recording metrics |
| `learning_ahead_rounds` | Indicate recording/learning mismatch and await convergence | Mixing an ahead learning observation into completed-round focus |
| `first_fixed_round` and `current.fixed` | “First fixed in round 2; currently not fixed” for the real after-block habit | Treating first-fixed history as current success; latest `regressed=false` does not undo an earlier regression |
| `synthetic=true` / null | Persistent “Synthetic example” / “Source type unknown” | Calling synthetic data recorded human improvement, or unknown mode real |
| `report.status=unavailable` or `invalid` | Event-only detail using the moment's embedded event and source reference | Requiring a report to view evidence |
| `available_unverified_revision` | Explain that report revision is unverified | Using the report to change the recommendation or asserting source alignment |
| Mixed moment | Show each `metric_outcomes` entry: low block success and punish failure can coexist | One success badge that conceals the missed punish |

The real fixture's 1/4 throw-break rate is an early signal under the five-observation focus policy. It is still the correct measured fraction. The synthetic fixture's automatic low-defense focus reflects all completed rounds, even though the final planted round shows improvement; first/current learning is a separate producer observation.

## Event selection and refresh

Each moment already contains an event summary, metrics and source reference. Selecting it can show those fields in place. Evidence is identified by session, source hash and original line; frame alone is insufficient. If fetching the brain's existing recording for deeper inspection, verify the source revision before resolving a line. No new evidence-lookup HTTP route exists.

Invalidate on the existing summary/reconnect/session triggers. Associate responses and selection with the selected session and requested view. A changed `snapshot_id` clears stale moment selection. Limits and manual focus can change a view without changing the source snapshot; do not merge the result into a previous view solely because snapshot IDs match. On errors, a retained old snapshot must be labelled stale. Pending learning is a valid partial snapshot, not an HTTP failure by itself.

## Eric's review and Chloe's acceptance checklist

Eric verified all eleven fixture states against the production builder, schema and drift test. Real counts are 0/16, 1/4 and 0/6. Invalid source suppresses focus; an orphan throw break invalidates its metric independently of overall parse quality; pending/current examples have identical recording counts and different source snapshots; mixed moments retain distinct outcomes. This is backend/example review. Chloe's intent/spec review and rendered acceptance remain open.

For Chloe's bounded first pass:

1. Review the fixture/state table and return ambiguous fields before changing app code. C3 in the revised plan (estimated-effectiveness wording/accessibility) is independent of these examples.
2. Following `app/AGENTS.md`, render the approved subset from fixtures with live insights disabled until the shared interface is agreed.
3. At 1920×1080, capture real, early/no opportunities, invalid, manual, pending/current and synthetic states. Check that fractions and pending labels are readable, long reasons wrap, and selection works by keyboard with visible focus. Use text or icons alongside color for status.
4. Select a mixed moment and verify its two outcomes. Select an event while report is unavailable. Change session/snapshot and verify selection is cleared appropriately.
5. Run app typecheck/build and record which states were actually observed. Growing-session/reconnect/voice acceptance requires the host run in [INTEGRATION.md](../INTEGRATION.md).

```sh
.venv/bin/python -m analytics.insight_examples --check
```

Expected: all eleven examples match. Chloe can start the review from the published branch without copying Eric's ignored local exports or obtaining Sahil's live folder.
