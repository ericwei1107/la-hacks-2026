# Draft contract change: GET /insights/{session_id}

**Status: draft for four-owner review. Nothing here is in `contracts/`.** Eric sends the request below; the contracts PR is opened only after Sahil, Garrett, Chloe and Eric have each approved. Until then the route stays behind `KUMITE_EXPERIMENTAL_INSIGHTS=1` (real analytics) and `--experimental-insights` (mock), and the app keeps its insights source off.

## Approvals

| Owner | Status |
| --- | --- |
| Sahil | **Approved with conditions** (October 18): the route is additive on :8767; it reads only files the brain already writes under `DATA_DIR` (recordings, sessions, learning, profiles, eval); nothing under `contracts/` changes. One point needs his confirmation, below |
| Garrett | Pending |
| Chloe | Pending (asleep; Eric collects later) |
| Eric | Proposer |

Against Sahil's conditions:

- **Additive on :8767:** met. No existing route changes.
- **Reads only brain-written files under `DATA_DIR`:** met. The route reads only `sessions/`, `recordings/`, `learning/` and `eval/` under `DATA_DIR`. `report` was removed from v1 and the route no longer opens replay reports; a session whose recording resolves outside `DATA_DIR` returns 503. Both are tested (`test_route_reads_only_brain_files_under_data_dir`, `test_route_refuses_a_recording_outside_data_dir`).
- **Nothing under `contracts/` changes:** conflicts with registering the route after approval, which adds `contracts/insights.schema.json`, `contracts/examples/insights.json` and one row to `contracts/api.md`. Needs Sahil to say whether additions are acceptable, or whether the route stays documented only in `analytics/`.

## What the contracts PR would contain

1. `contracts/insights.schema.json`: a copy of [`analytics/insights_v1.schema.json`](../insights_v1.schema.json), with title `SessionInsights` and description `GET /insights/{session_id} response (analytics :8767).` No other change.
2. `contracts/examples/insights.json`: a copy of [`analytics/fixtures/insights/public/real.json`](../fixtures/insights/public/real.json), the real M3 session's view (0/16 lows, 1/4 throws, 0/6 estimated punishes, low-defense focus).
3. One row in the Analytics table of `contracts/api.md`:

```md
| GET | `/insights/{session_id}` | `?limit=1..50` optional, default 5 moments | `insights.schema.json`; 404 unknown session, 422 bad id or limit, 503 sources unavailable or changing |
```

`contracts/validate.py` discovers schemas automatically and requires the matching example. A dry run with exactly these three changes on a scratch copy of `contracts/` passed all ten examples, including `examples/insights.json`. Existing routes, schemas and examples are unchanged.

After the merge: the flag defaults on in real and mock analytics, the route tests validate against `contracts/insights.schema.json`, and Chloe switches her insights source to the live route.

## What owners are agreeing to

| Owner | What to check |
| --- | --- |
| Chloe | The fields cover the focus card, evidence list, moments and freshness states in [insights-ui.md](insights-ui.md); the [TypeScript type](../INSIGHTS_PROPOSAL.md#typescript-type-for-the-public-v1-view) is usable |
| Garrett | `focus.action` stays draft (`action_reviewed: false`) until he approves wording; punishment focus stays disabled; `estimated: true` marks punish conversion as an estimate |
| Sahil | The route only reads files the brain already writes; no producer change or game-loop work is required |
| Eric | Same builder for export, real and mock; counts cover all completed rounds regardless of `limit` |

Freezing this does not freeze internal export fields, the focus rule or the five-observation threshold; those carry their own version numbers.

## Request to send (Eric)

> Proposing one additive analytics route for the focus card: `GET /insights/{session_id}`. It returns defense counts with linked evidence, the suggested focus, first/current habit status, a few key moments and freshness, built from files the brain already writes. No existing route changes and no producer change is needed.
>
> Schema, example and display rules: PR #22's follow-up branch `track-d-insights-v1`, files `analytics/insights_v1.schema.json`, `analytics/fixtures/insights/public/real.json` and `analytics/handoffs/insights-ui.md`. It's already runnable behind a flag (`KUMITE_EXPERIMENTAL_INSIGHTS=1`), off by default.
>
> Could each of you reply approve or request changes? Chloe: does it cover what the card needs? Garrett: action text stays marked unreviewed until you approve it, and punish focus stays off. Sahil: it only reads existing files. Once all four approve I'll open the contracts PR (schema, example, one `api.md` row).
