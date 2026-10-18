# Draft contract change: GET /insights/{session_id}

**Status: draft for four-owner review. Nothing here is in `contracts/`.** Sahil has approved the route and the `contracts/` additions; Chloe has approved the route (with `focus.min_opportunities`) and the `contracts/` additions; Garrett approved the route before `focus.min_opportunities` was added and still needs to accept that field and say yes to the `contracts/` additions. The contracts PR is opened only after Sahil, Garrett, Chloe and Eric have each approved. Until then the route stays behind `KUMITE_EXPERIMENTAL_INSIGHTS=1` (real analytics) and `--experimental-insights` (mock), and the app keeps its insights source off.

## Approvals

| Owner | Status |
| --- | --- |
| Sahil | **Approved, including the `contracts/` additions** (October 18). Route: additive on :8767, reads only files the brain already writes under `DATA_DIR`. Contracts: adding `contracts/insights.schema.json`, its example and one new `api.md` row is fine, provided nothing existing is edited and `python contracts/validate.py` passes in the same commit |
| Garrett | **Route approved** (October 18, Track C): no additional fields; keep it opt-in until all four approve; this does not approve the current punish calculation. **Pending:** his approval predates `focus.min_opportunities`, which his "no additional fields" condition covers, so he needs to accept that field; and his yes on the `contracts/` additions (Sahil asked for it, per `api.md`). On October 18 he asked which field was meant, because the pushed branch (`95b65a6`) does not have it yet |
| Chloe | **Approved with one condition, now met** (October 18): add `focus.min_opportunities` so the app doesn't copy the threshold. Added as a required integer in v1; it's additive, so tell Sahil and Garrett. Her optional move-name request is deferred. Eric relayed her yes to the `contracts/` additions on October 18 |
| Eric | Proposer |

Against Sahil's conditions:

- **Additive on :8767:** met. No existing route changes.
- **Reads only brain-written files under `DATA_DIR`:** met. The route reads only `sessions/`, `recordings/`, `learning/` and `eval/` under `DATA_DIR`. `report` was removed from v1 and the route no longer opens replay reports; a session whose recording resolves outside `DATA_DIR` returns 503. Both are tested (`test_route_reads_only_brain_files_under_data_dir`, `test_route_refuses_a_recording_outside_data_dir`).
- **`contracts/`:** resolved. Sahil accepts the three additions below on two conditions: no existing schema, example, row or line is edited, and `python contracts/validate.py` passes in the same commit as the additions.

## What the contracts PR would contain

1. `contracts/insights.schema.json`: a copy of [`analytics/insights_v1.schema.json`](../insights_v1.schema.json), with title `SessionInsights` and description `GET /insights/{session_id} response (analytics :8767).` No other change.
2. `contracts/examples/insights.json`: a copy of [`analytics/fixtures/insights/public/real.json`](../fixtures/insights/public/real.json), the real M3 session's view (0/16 lows, 1/4 throws, 0/6 estimated punishes, low-defense focus).
3. One row in the Analytics table of `contracts/api.md`:

```md
| GET | `/insights/{session_id}` | `?limit=1..50` optional, default 5 moments | `insights.schema.json`; 404 unknown session, 422 bad id or limit, 503 sources unavailable or changing |
```

`contracts/validate.py` discovers schemas automatically and requires the matching example. A dry run with exactly these three changes on a scratch copy of `contracts/` (identical to `origin/main` on October 18) passed all ten examples, including `examples/insights.json`; `diff -r` showed two new files and one added `api.md` line, with no existing line changed. The punish v6 `public/real.json` (`bac884f`) also validates against the proposed schema, so the example is copied from whichever `public/real.json` is current when the PR is opened.

The contracts PR is a single commit with exactly these three additions. Before committing: `git diff --cached --stat -- contracts/` lists only the two new files and `api.md`, `git diff --cached -- contracts/api.md` shows one `+` line and no `-` line, and `python contracts/validate.py` prints `PASS`.

After the merge: the flag defaults on in real and mock analytics, the route tests validate against `contracts/insights.schema.json`, and Chloe switches her insights source to the live route.

## What owners are agreeing to

| Owner | What to check |
| --- | --- |
| Chloe | The fields cover the focus card, evidence list, moments and freshness states in [insights-ui.md](insights-ui.md); the [TypeScript type](../INSIGHTS_PROPOSAL.md#typescript-type-for-the-public-v1-view) is usable |
| Garrett | Action wording approved (low and throw defense; generic punish text acceptable), so `action_reviewed` is true; punishment focus stays disabled until the corrected metric is verified; `estimated: true` marks punish conversion as an estimate |
| Sahil | The route only reads files the brain already writes; no producer change or game-loop work is required |
| Eric | Same builder for export, real and mock; counts cover all completed rounds regardless of `limit` |

Freezing this does not freeze internal export fields, the focus rule or the five-observation threshold; those carry their own version numbers.

## Request to send (Eric, already sent)

> Proposing one additive analytics route for the focus card: `GET /insights/{session_id}`. It returns defense counts with linked evidence, the suggested focus, first/current habit status, a few key moments and freshness, built from files the brain already writes. No existing route changes and no producer change is needed.
>
> Schema, example and display rules: PR #22's follow-up branch `track-d-insights-v1`, files `analytics/insights_v1.schema.json`, `analytics/fixtures/insights/public/real.json` and `analytics/handoffs/insights-ui.md`. It's already runnable behind a flag (`KUMITE_EXPERIMENTAL_INSIGHTS=1`), off by default.
>
> Could each of you reply approve or request changes? Chloe: does it cover what the card needs? Garrett: action text stays marked unreviewed until you approve it, and punish focus stays off. Sahil: it only reads existing files. Once all four approve I'll open the contracts PR (schema, example, one `api.md` row).

## Follow-up to Garrett (Eric)

> The field is `focus.min_opportunities`: a required integer (minimum 1, currently 5) on the `focus` object. It's the number of observations a metric needs before it can be picked as the automatic focus, so the app can show "3 lows seen, need 5" without copying the backend rule. Chloe asked for it as her approval condition. Nothing else changed: no existing field was renamed, removed or retyped, and the internal export already had the threshold. It isn't on the pushed branch yet (PR #25 is at `95b65a6`); it's commit `55a50e4`, which I'll push shortly. Then it's in `analytics/insights_v1.schema.json` under `focus.required` and in `analytics/fixtures/insights/public/real.json` as `"min_opportunities": 5`.
>
> Since your approval said no additional fields: are you OK with this one, and is adding the contract (`contracts/insights.schema.json`, its example, one new `api.md` row, nothing existing edited) a yes? Sahil and Chloe have both said yes.
