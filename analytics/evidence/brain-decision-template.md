# Brain decision evidence return handoff

**Status: pending owner implementation and real runtime evidence.** This template is not a verification result. Fill it from the actual game process after configuring the corrected full brain DSN. Do not include credentials, environment dumps or raw session payloads.

## Run identity and configuration

| Field | Owner-provided value |
| --- | --- |
| Code branch/PR and full deployed main commit | Pending |
| Launch entry point/process that initializes the SDK | Pending |
| Machine / OS / Python / SDK versions | Pending |
| Session, round and workload/configuration | Pending |
| Run date/time and timezone | Pending |
| Actual Sentry release and environment | Expected release = full deployed main SHA; environment = demo-laptop; runtime verification pending |
| Configured root transaction sampling | Expected 0.05; verify deployed configuration |
| Transport mode during run | Pending |

## Retained trace and waterfall

- Direct `kumite-brain` decision trace URL: pending.
- Matching waterfall screenshot path under `analytics/evidence/`: pending.
- Confirm the actual read, decode, reflex, tactical and input operations are children of the selected decision; record any missing/conditional operation honestly.
- Confirm the screenshot and trace show the same trace ID, full deployed main SHA as release and `demo-laptop` environment. Captured `development` or generic `demo` evidence does not satisfy this particular promised brain run.
- Record where the transaction starts/ends across the snapshot-generator boundary. Empty placeholder spans and a later transaction that excludes the read do not satisfy the pipeline requirement.
- Confirm configuration from deployed code/launch settings. One sampled trace does not measure or prove a 5% sampling fraction.

## Comparable on/off timing

Use the same named frame/poll timing measurement, machine, workload and observation duration for both runs. State whether “off” disables instrumentation or only SDK transport; sampling 0 with wrappers still active is a different control. Include any metric unavailable from the current measurement rather than inventing it.

Sahil's promised minimum is **decision-loop p50/p95 in milliseconds, one practice round each way, same settings, on-run sampling 5%**. Retain round duration and measurement count even if the round lengths differ; describe differing workload rather than claim identical observations. This small comparison does not establish general timing reliability.

| Measurement | Tracing off | Tracing on at 5% |
| --- | --- | --- |
| Duration and sample count | Pending | Pending |
| p50 decision-loop duration (ms) | Pending | Pending |
| p95 duration (ms) | Pending | Pending |
| Maximum duration (ms) | Pending | Pending |
| Missed frames / overruns, with definition | Pending | Pending |
| Same workload/configuration confirmed | Pending | Pending |

Network-unavailable behavior and whether SDK transport blocks the hot loop: pending. Kill-switch and pad-release behavior with telemetry disabled/unavailable: pending. **Sahil's acceptable-overhead decision and rationale: pending.** No new numerical safety threshold is imposed by this template.

## Track D verification

Eric records the inspection date, direct retained trace result, five-operation parentage, screenshot identity, sampling configuration evidence and timing review here or in `SENTRY_VERIFICATION.md`. Source merged, SDK configured, evidence retained and demo-host acceptance are separate statuses. Keep overall B5 open until real owner artifacts have been checked; keep native/demo verification open until it actually runs.
