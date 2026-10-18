# Brain decision evidence: October 18, 2026

Filled from Sahil's return (about 04:05 PT, repeated later in chat) using the [template](brain-decision-template.md). Track D checked the trace with Sentry MCP and the configuration in the deployed source. Timings are owner measurements; Sentry cannot show the tracing-off run.

## Run identity and configuration

| Field | Value | Checked by Track D |
| --- | --- | --- |
| Deployed commit | `e8f134fbceedd63607cf27acfbce7ea2067d24d3` on `main` ("Sentry decision tracing and --timing for the hot loop") | Ancestor of `origin/main` confirmed |
| SDK initialization | `game/trace.py` `init()`, called once at the top of `game.bot` main, only when `SENTRY_DSN` is set | Source inspected at `e8f134f` |
| Release / environment | Release = `git rev-parse HEAD`; environment constant `demo-laptop` | Source, and every span in the trace |
| Root sampling | `SAMPLE_RATE = 0.05`, `auto_enabling_integrations=False` | Source; trace spans show `client_sample_rate 0.05` |
| Workload | Practice mode, Devil Jin vs Kazuya L3, seed 7, laptop SMEHTA2004, about 45 s per run | Owner-reported |

## Retained trace

- Trace: https://university-of-maryland-ma.sentry.io/explore/traces/trace/c5e0b584bce7432a85d45b3f30eedf3a/ (project `kumite-brain`, 2026-10-18 10:56:06 UTC).
- Structure: one `game.decision` transaction (op `decision`, 0.67 ms) with children `game.read` (0.17 ms), `game.tactical` (0.10 ms), `game.decode` (0.06 ms), `game.reflex` (0.01 ms) and `game.input` (0.01 ms). All five required operations are present as children. No errors.
- Every span: release `e8f134fbceedd63607cf27acfbce7ea2067d24d3`, environment `demo-laptop`, client sample rate 0.05.
- Transaction boundary (source): `hotloop.frames` opens the decision transaction before the snapshot read and keeps it open across the generator yield. It finishes when the generator resumes (ok) or is closed (cancelled). Frames that never yield are dropped.
- Waterfall screenshot: [brain-decision-waterfall-2026-10-18.png](brain-decision-waterfall-2026-10-18.png). It shows the same trace ID `c5e0b584bce7432a85d45b3f30eedf3a`, release `e8f134fbceed`, environment `demo-laptop`, CPython, 6 spans, 0.67 ms root duration, the five child spans under `decision`, and `client_sample_rate 0.05` in the span attributes. No keys or DSN are visible.
- One sampled trace confirms the configured rate on its spans. It does not measure the realized sampling fraction.

## Tracing off / on timing

Same `--timing` measurement in both runs: `perf_counter` around every complete frame iteration on the same code path. "Off" means `SENTRY_DSN` unset, so the SDK is not initialized and every span is a no-op.

| Measurement | Tracing off | Tracing on at 5% |
| --- | --- | --- |
| Sample count (frames) | 2573 | 2627 |
| p50 (ms) | 0.517 | 0.698 |
| p95 (ms) | 0.838 | 1.398 |
| Max (ms) | 37.3 | 39.0 |
| Frames over 16.7 ms | 1 | 1 |
| Missed frames (loop counter) | 2 | 2 |

Difference: p50 +0.18 ms, p95 +0.56 ms. Both percentiles stay far below the 16.7 ms frame budget, and frames over budget and missed frames are equal in both runs. This is one practice round each way, not a general timing benchmark.

## Still open

- Sahil's explicit overhead-acceptance statement; he reported the numbers but did not state a judgment.
- Behavior when Sentry is unreachable (does transport ever block the hot loop?) was not reported.

## Status

Brain decision trace **verified**: structure, release, environment and configured sampling. Timing comparison **received** (owner-measured). Waterfall screenshot **retained**. B5 closes once Sahil confirms the overhead is acceptable. Independent per-service traces still do not establish cross-service propagation.
