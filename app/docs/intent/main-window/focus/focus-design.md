---
parent: main-window
prefix: MAIN-FOCUS
---

# Focus card

## Context and Design Philosophy

The focus card tells the player what to practice from the selected set, and shows the exchanges behind that choice. It sits at the top of the Stats screen, above the headline numbers, with the evidence and the set's key moments beneath it.

The analytics service decides everything that is judgment: which metric is the focus, why, the counts, which exchanges are evidence, and whether the advice text has been reviewed (HLD tenet, arithmetic in the app, judgment in the services). The card only words and arranges what `GET /insights/{session_id}` returns. It never picks a focus, recounts from the evidence list, or turns a missing value into a number.

The insights route is not yet a shared contract. Until all four owners agree to it, the card is off unless `KUMITE_INSIGHTS=1` is set in the environment or `app/.env`; with it off, the Stats screen is exactly as before.

## Source

- The card requests `GET /insights/{session_id}?limit=3` from the analytics service for the selected set, as the public v1 view (`analytics/insights_v1.schema.json`, `analytics/INSIGHTS_PROPOSAL.md`). Real analytics serves it only with `KUMITE_EXPERIMENTAL_INSIGHTS=1` on its side; the mock serves it with `--experimental-insights`.
- The shell passes the switch to the page as a resolved setting, like the overlay mode, and the service clients own the call and its query.
- A reply is used only when its `session_id` is the selected set.

## The card

On the surface tone with a hairline border; the screen's one indigo frame stays the across-sessions chart:

- **Heading:** "What to practice". A manual focus (`focus.mode = manual`) adds "Selected focus".
- **The focus metric**, when `focus.metric` is set: its label (`metrics[focus.metric].label`) and its fraction in words, from the supplied counts, with the percentage beside it when `value` is a number:
  - low defense: "<successes> of <opportunities> lows blocked";
  - throw defense: "<successes> of <opportunities> throws broken";
  - punish conversion: "<successes> of <opportunities> punishes landed", always under "Estimated".
- **Why:** `focus.reason`, in muted text.
- **What to do:** `focus.action` when `focus.action_reviewed` is true; otherwise the neutral "Review these moments", because the wording has not been reviewed.
- **No focus** (`focus.metric` null): `focus.reason` as the card's line (for example "More observations needed"). Each metric still shows its own state below.
- **Metric states**, one compact row per metric under the focus:
  - observed: its fraction and percentage;
  - early signal: "<opportunities> <noun> seen; need <threshold> for an automatic focus", where the threshold comes from the reply; without it, "<opportunities> <noun> seen; more needed for an automatic focus";
  - no opportunities: "No opportunities observed" with "—";
  - invalid: "Data needs review", with no rate and no advice for that metric.
- **Bad source** (`quality = invalid`): no focus, no action and no metric rates; the card reads "This set's data needs review before it can suggest a focus."
- **Source type:** `synthetic = true` shows a persistent "Synthetic example" tag; `synthetic = null` shows "Source type unknown".

A null value is never drawn as 0%, and a fraction is never computed from the evidence list.

## Evidence and moments

Beneath the card, two lists, each row a button:

- **Evidence**, for the focus metric (or, with no focus, the metric with the most opportunities): its evidence rows, with "Showing <n> of <evidence_total>". Each row reads "Round <r>, frame <f>: <event>", for example "Round 2, frame 460: low counter-hit, 12 damage", with the outcome as a word ("Blocked", "Missed", "Broken", "Not broken", "Punished", "Not punished") as well as a mark, never color alone.
- **Moments**, the set's moments in the reply's order, with "Showing <n> of <moments_total>". A mixed moment lists each entry of `metric_outcomes` with its own outcome word.
- The event wording is a fixed template over the event summary: hit level, the kind ("hit", "counter-hit", "block", "throw", "throw break", "whiff"), damage when above zero, and the frame advantage on a block. A missing frame reads "frame —".
- **Selecting** a row (click, Enter or Space) expands it in place with the event's fields and, when present, the response location. Detail is event-only: v1 carries no report, and the card never waits for one.
- A selection is identified by its set and line. It is kept while that set stays selected and its line still appears in the latest reply, including after the recording grows. It is cleared when the set changes or the line disappears.

## Freshness

- The card refetches on the same triggers the frame uses for stats and learning: a round summary for the set, a new live set, the end of a live round, and the round-catch-up re-poll.
- A line under the card reads "Through completed round <n>" from `freshness.latest_completed_round`, or "No completed rounds yet".
- While `pending_learning_rounds` is non-empty: "Round <n> learning is still being saved." The defense counts stay on screen; they are valid meanwhile.
- While `learning_ahead_rounds` is non-empty: "Learning is ahead of the recording; waiting for it to catch up."
- On a 503 or an unreachable service, the last good view stays, labelled "Not up to date", and the next trigger retries. Before any good view, the card shows skeleton lines while the request is pending, then a muted line: "Insights come back when analytics reconnects." when analytics is offline, "Analytics has no insights for this set yet." for a 404, and "Insights aren't available for this set right now." otherwise.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Placement | Top of Stats, evidence and moments beneath | Learning; a new screen | Stats already holds the set's counts; the focus is their "so what". A new screen is out of scope for the first release. |
| Switch | `KUMITE_INSIGHTS=1`, off by default | Always on; a Controls toggle | The route is not an agreed contract. A setting read like the overlay mode keeps it one line away for development and the demo, and off for everyone else. |
| Fraction wording | Fixed templates per metric over supplied counts | Showing `focus.reason` alone | Templates are arithmetic over the reply (allowed by the HLD tenet) and read plainly; the reason stays as the "why". |
| Unreviewed action | "Review these moments" | Showing draft text marked "draft" | Unreviewed mechanics must not reach players as advice. |
| Early-signal threshold | From the reply | A constant 5 in the app | The threshold is the analytics service's policy; copying it would let the two drift. |
| Selection identity | Set and line | Frame; snapshot id | A frame is not unique, and a growing recording changes the snapshot without moving earlier lines. |
| Error handling | Keep the last good view, labelled | Blank the card | A brief outage mid-set should not erase the advice the player is reading. |

## Open Questions & Future Decisions

1. The reply has no early-signal threshold; requested from Eric as an additive field. Until then the early-signal line omits the number.
2. Events carry `move_id` only. A move name or notation would make evidence rows clearer; requested as optional.
3. `focus.reason` is written for review ("0/16 successful observed opportunities; 16 failures"). Player-facing wording may follow once the contract settles.

## References

- `../main-window-design.md`; `../stats/stats-design.md`; `../frame/frame-design.md` (refresh triggers)
- `../../service-clients/service-clients-design.md`; `../../shell/shell-design.md` (the switch)
- Eric's branch `track-d-insights-v1`: `analytics/insights_v1.schema.json`, `analytics/INSIGHTS_PROPOSAL.md`, `analytics/handoffs/insights-ui.md`, `analytics/fixtures/insights/public/`
