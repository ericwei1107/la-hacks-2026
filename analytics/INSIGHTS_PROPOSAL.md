# Session insights interface proposal

**Status: implemented internal export; shared HTTP contract not approved or registered.** Sahil, Chloe, Garrett and Eric must agree before any app/shared-sidecar consumption or public route is added. The schema beside the implementation is an internal draft, outside frozen `contracts/`.

## Reproduce the reviewable result

```sh
.venv/bin/python -m analytics.insights 2026-10-18T05-14-03_sahil_djin_vs_kaz --data-dir ./data/samples/live_learning --output-dir ./data/analytics
```

This writes deterministic JSON and Markdown under ignored `data/analytics/`, with 0/16 lows, 1/4 throws, 0/6 estimated punishes and automatic low-defense focus. Generated exports must not be written into checked-in sample bundles; choose an explicit output directory for those inputs.

Optional `--limit` is 1–50 (default ten moments); `--focus low_defense` or `--focus throw_defense` selects a usable metric manually. Internal punishment focus stays disabled pending Garrett review. The command initializes neither telemetry nor a database connection, even if their environment variables are set. It has no provider/model dependency.

## Proposed additive HTTP surface

After all-owner agreement, add `GET /insights/{session_id}?limit=5` to real analytics and mock analytics using the same snapshot builder and the minimal view described below. No existing route or response changes. Add the agreed schema/example/API documentation together before consumer implementation. No write endpoint or background model invocation is proposed. Five is the proposed public default; the existing internal CLI defaults to ten.

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

These are full internal snapshots using the existing internal schema. The proposed minimal public v1 view keeps identity/version, freshness, quality state, the three metrics, focus, first/current habits, moments and report status. Top-level source byte counts/hashes, tactical counts, per-round blocks and bandit estimates can remain internal. Each evidence reference retains its opaque source hash so a frame/line cannot be mistaken for an identity across revisions. A public projection has not been implemented or approved.

Review examples contain at most five moments and three evidence rows per metric. The internal CLI currently defaults to ten moments; the proposed public default of five remains a review decision. Counts always cover the full completed-round population. `snapshot_id` identifies source revisions and implementation versions; changing limit or manual focus changes the view without changing that source identity. Bind a selected moment to its session, source identity and line, and clear it when that identity changes.

The action strings are marked `draft_awaiting_Garrett_review`. Until Garrett approves mechanical wording, a candidate card can show the metric fraction, the supplied reason and neutral “Review these moments” text. The fixture package records Eric's review; it does not imply Chloe or the other owners have accepted the interface.

## TypeScript review sketch

This structural subset describes fields already present in the checked-in fixtures; additional internal fields may be ignored. It is a draft for Chloe to review in her intent workflow, not code installed in `app/` or a shared contract. A public HTTP schema and error handling must be agreed before live wiring.

```ts
type MetricKey = 'low_defense' | 'throw_defense' | 'punish_conversion'
type MetricState = 'observed' | 'early_signal' | 'no_opportunities' | 'invalid'

interface SourceReference {
  session_id: string
  source: 'recording'
  sha256: string
  line: number
  round: number
  frame: number | null
}

interface MetricEvidence {
  label: string
  successes: number
  opportunities: number
  failures: number | null
  value: number | null
  state: MetricState
  estimated: boolean
  evidence_total: number
  evidence: Array<{
    opportunity: SourceReference
    response: SourceReference | null
    outcome: 'success' | 'failure'
  }>
}

interface HabitObservation {
  round: number
  fixed: boolean | null
  regressed: boolean
  n: number | null
  p: number | null
  mastery: number | null
  action: string | null
}

interface Moment {
  reference: SourceReference
  metrics: MetricKey[]
  outcome: 'success' | 'failure' | 'damage' | 'mixed'
  response: SourceReference | null
  metric_outcomes: Partial<Record<MetricKey, {
    outcome: 'success' | 'failure'
    response: SourceReference | null
  }>>
  event: {
    kind: string
    actor?: 0 | 1
    target?: 0 | 1
    damage?: number
    hit_level?: string
    move_id?: number
    frame_advantage?: number | null
  }
}

interface InsightReview {
  format_version: 1
  snapshot_id: string
  session_id: string
  synthetic: boolean | null
  freshness: {
    latest_recording_round: number | null
    completed_rounds: number[]
    latest_learning_round: number | null
    pending_learning_rounds: number[]
    learning_ahead_rounds: number[]
  }
  quality: { state: 'observed' | 'pending' | 'invalid' }
  metrics: Record<MetricKey, MetricEvidence>
  focus: {
    mode: 'automatic' | 'manual'
    metric: MetricKey | null
    reason: string
    action: string | null
    action_status?: 'draft_awaiting_Garrett_review'
  }
  learning: {
    habits: Record<string, {
      first_detected_round: number | null
      first_fixed_round: number | null
      current: HabitObservation | null
    }>
  }
  moments: Moment[]
  moments_total: number
  report: { status: 'unavailable' | 'invalid' | 'available_unverified_revision' }
}
```
