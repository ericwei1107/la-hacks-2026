# Session insights interface proposal

**Status: internal export implemented; public v1 view implemented behind opt-in flags; shared HTTP contract not approved.** Sahil, Chloe, Garrett and Eric must agree before the route is enabled by default, added to frozen `contracts/`, or consumed by the shipped app. Eric chose a minimal public v1 view (decision D2) and an opt-in experimental route for development before agreement (decision D1). Both schemas live beside the implementation, outside `contracts/`.

The implementation, generated fixtures and review guide are fetchable from [PR #22](https://github.com/ericwei1107/la-hacks-2026/pull/22), branch `track-d-insights-host-handoff`.

## Reproduce the reviewable result

```sh
.venv/bin/python -m analytics.insights 2026-10-18T05-14-03_sahil_djin_vs_kaz --data-dir ./data/samples/live_learning --output-dir ./data/analytics
```

This writes deterministic JSON and Markdown under ignored `data/analytics/`, with 0/16 lows, 1/4 throws, 0/6 estimated punishes and automatic low-defense focus. Generated exports must not be written into checked-in sample bundles; choose an explicit output directory for those inputs.

Optional `--limit` is 1–50 (default ten moments); `--focus low_defense` or `--focus throw_defense` selects a usable metric manually. Internal punishment focus stays disabled pending Garrett review. The command initializes neither telemetry nor a database connection, even if their environment variables are set. It has no provider/model dependency.

## Proposed additive HTTP surface

`GET /insights/{session_id}?limit=5` returns the public v1 view (`analytics/insights_v1.schema.json`) built by `analytics.insights.public()` from the same snapshot builder as the export. `limit` is 1–50 moments, default 5. Errors: 404 unknown session, 422 invalid session id or limit, 503 when sources are unavailable, invalid or still changing (bounded message, no paths or credentials). No existing route or response changes; no write endpoint or model call.

Before agreement the route is **off by default** and exists only for development:

| Service | Enable | Notes |
| --- | --- | --- |
| Real analytics | `KUMITE_EXPERIMENTAL_INSIGHTS=1` in the launch environment | Reads the service's `DATA_DIR`, including growing live files |
| Mock analytics | `python tools/mock/serve.py --experimental-insights` | Reads `DATA_DIR`; sessions loaded only through `--recording` outside it return 404 |

The shipped app keeps its insights source disabled until all four owners approve. After approval, the schema becomes `contracts/insights.schema.json`, the route row is added to `contracts/api.md`, and the flag defaults on. `python -m analytics.insights <session> --data-dir <dir> --public` prints the same v1 JSON without starting a server.

## Internal export fields

The full builder/export and review fixtures contain the fields below. The proposed public view is a subset; a fixture's extra internal fields are not a promise that the live route will expose them.

| Field | Meaning |
| --- | --- |
| `format_version`, `calculation_version`, `rule_version` | Independent format, existing persisted-calculation and focus-policy identities |
| `snapshot_id` | Content fingerprint of source revisions and versions; no generation clock or absolute path |
| `session_id`, `synthetic`, `population` | Identity, explicit synthetic marker and `completed_rounds` population |
| `sources` | Metadata/recording/learning/evaluation/report availability, consumed-prefix SHA-256, bytes and pending-tail flags |
| `freshness` | Recording round, closed recording rounds, available learning round, missing/ahead learning rounds |
| `quality` | Invalid-record counts/positions, unsupported record count and pending/invalid state; retests remain unavailable |
| `metrics` | Low/throw/estimated-punish counts, nullable value, state, anomalies and limited cited evidence |
| `rounds`, `rounds_total` | Last fifty completed-round metric blocks and total completed-round count |
| `focus` | Deterministic recommendation/reason; drafted action text is explicitly unreviewed |
| `learning` | First/current habit distinction, last fifty online accuracy observations, bandit estimates and nullable eval |
| `tactical` | Narrowly validated recorded choices/source counts, never hit rates or calibrated probabilities |
| `moments`, `moments_total` | At most `limit` useful cited events and full candidate count |
| `report` | Availability/validation status; reports are not used for recommendations because their recording revision is unverified |

Every metric includes `successes`, `opportunities`, `failures`, `value`, `state`, `definition_version`, `estimated`, `anomalies`, `evidence_total` and sampled `evidence`. A reference contains `{session_id, source, sha256, line, round, frame}`. Counts cover the complete declared population; response limits do not change them.

## Source consistency and failure behavior

Capture metadata and required recording plus optional companions, then recheck all file identities/sizes/timestamps. Retry one changing capture. Schema validation and hashes protect the captured content; caches use content fingerprints, including in-place same-size corrections. References use original line positions and recording-prefix identity.

Recording analysis consumes only newline-terminated records, matching live stats. Partial JSON/UTF-8 companion tails wait for completion. Complete malformed recording lines are counted and invalidate recommendations; invalid complete learning/evaluation returns a data error. Unknown extensions remain unsupported without changing global recording readers.

Missing optional learning/eval/report leaves valid defense counts usable. Missing latest learning is pending, not zero. Learning ahead of recording is labelled and not used as completed-round evidence. Invalid reports are isolated; existing reports do not establish a matching recording revision.

The proposed route maps unknown sessions to 404, invalid identifiers/query values to 422, and unavailable/unstable required or invalid strict companion data to 503 with bounded diagnostics. A future evidence lookup must compare the current snapshot/source fingerprint and reject stale references; the internal `resolve` method already does this and returns the nearest preceding same-round state when available.

JSON and Markdown are individually written through temporary files plus atomic replacement. Both identify the same snapshot, allowing readers to detect an interrupted two-file publication; this is not a filesystem transaction across both files.

## Approval and remaining work

The proposed route is deliberately absent until agreement is retained. Export, source auditing and focus tests can ship independently. After approval, wire real/mock handlers, validate against the agreed shared schema, test route parity and malformed/missing data cases, and let Chloe review a concrete optional C3 increment. Chloe's C1/C2 work continues on frozen APIs.

## Concrete review package for Chloe

The [fixture index](fixtures/insights/README.md) links eleven checked-in examples produced by the real builder. [Display rules and acceptance cases](handoffs/insights-ui.md) explain every state and the evidence/event-only interaction. Regenerate or check them with:

```sh
.venv/bin/python -m analytics.insight_examples
.venv/bin/python -m analytics.insight_examples --check
```

The top-level files are full internal snapshots. `fixtures/insights/public/` holds the public v1 view of each one, generated by `public()` and covered by the same drift check. Chloe builds against the public files. The v1 view keeps identity and version, `recording_sha256`, freshness, quality state, the three metrics with evidence and event summaries, focus, first/current habits, moments with per-metric outcomes, and report status. Source byte counts, tactical counts, per-round blocks, bandit estimates and habit probabilities stay internal; they can be promoted later through the same agreement. References are `{line, round, frame}` within the response's `recording_sha256`. Recordings only grow during play, so earlier lines stay valid as the hash changes; bind a selection to session and line, and drop it when the session changes or the location no longer appears in the response.

Review examples contain at most five moments and three evidence rows per metric. The internal CLI defaults to ten moments; the public route defaults to five. Counts always cover the full completed-round population. `snapshot_id` identifies source revisions and implementation versions; changing limit or manual focus changes the view without changing that source identity. Bind a selected moment to its session and line, and clear it when the session changes or the location no longer appears.

The action strings are marked `draft_awaiting_Garrett_review`. Until Garrett approves mechanical wording, a candidate card can show the metric fraction, the supplied reason and neutral “Review these moments” text. The fixture package records Eric's review; it does not imply Chloe or the other owners have accepted the interface.

## TypeScript type for the public v1 view

Chloe can paste this into the app's contract types during her intent workflow; Eric does not edit `app/`. It matches `analytics/insights_v1.schema.json`, and all eleven public fixtures type-check against it with `tsc --strict --noEmit`. It becomes binding only after the four-owner agreement.

```ts
type MetricKey = 'low_defense' | 'throw_defense' | 'punish_conversion'
type MetricState = 'observed' | 'early_signal' | 'no_opportunities' | 'invalid'

interface Location {
  line: number
  round: number
  frame: number | null
}

interface EventSummary {
  kind: string
  actor?: number
  target?: number
  damage?: number
  hit_level?: string
  move_id?: number | string
  frame_advantage?: number
}

interface Metric {
  label: string
  successes: number
  opportunities: number
  failures: number | null
  value: number | null
  state: MetricState
  estimated: boolean
  evidence_total: number
  evidence: Array<{
    opportunity: Location
    response: Location | null
    outcome: 'success' | 'failure'
    event: EventSummary
  }>
}

interface Habit {
  first_detected_round: number | null
  first_fixed_round: number | null
  current_round: number
  fixed: boolean | null
  regressed: boolean
  last_regressed_round: number | null
}

interface Moment {
  reference: Location
  metrics: MetricKey[]
  outcome: 'success' | 'failure' | 'mixed' | 'damage'
  response: Location | null
  event: EventSummary
  metric_outcomes: Partial<Record<MetricKey, { outcome: 'success' | 'failure'; response: Location | null }>>
}

interface InsightsV1 {
  format_version: 1
  snapshot_id: string
  session_id: string
  synthetic: boolean | null
  recording_sha256: string | null
  freshness: {
    latest_completed_round: number | null
    latest_recording_round: number | null
    latest_learning_round: number | null
    pending_learning_rounds: number[]
    learning_ahead_rounds: number[]
  }
  quality: 'observed' | 'pending' | 'invalid'
  metrics: Record<MetricKey, Metric>
  focus: {
    mode: 'automatic' | 'manual'
    metric: MetricKey | null
    state: 'observed' | 'early_signal' | null
    reason: string
    action: string | null
    action_reviewed: boolean
  }
  habits: Record<string, Habit>
  moments: Moment[]
  moments_total: number
  report: 'unavailable' | 'invalid' | 'available_unverified_revision'
}
```

The public view drops internal habit details (`n`, `p`, `mastery`, `action`); the existing `/learning` route continues to serve them. `focus.action_reviewed` stays `false` until Garrett approves the wording; show neutral "Review these moments" text until then.
