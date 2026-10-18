# Section 4.6: analytics endpoint tracing

The existing single `sentry_sdk.init` in `analytics/main.py` remains unchanged. FastAPI automatically enables its Sentry integration, with HTTP tracing enabled by the existing `traces_sample_rate=1.0` configuration. No duplicate initialization, manual HTTP wrapper, or project was added. See the [official FastAPI integration guide](https://docs.sentry.io/platforms/python/integrations/fastapi/).

## Local instrumentation verification

```sh
.venv/bin/python -m unittest discover -s analytics/tests -p test_sentry.py -v
```

An isolated subprocess replaces only the transport used by the application's existing initialization. It verifies exactly one initialization and one HTTP transaction for each of `/health`, `/stats/{session_id}`, `/learning/{session_id}` and `/trends/{player}/{character}`, with the expected environment/release tags. It sends no telemetry over the network.

## Live verification

```sh
.venv/bin/python analytics/tests/verify_sentry.py --live
```

The script starts the actual `analytics.main:app` on loopback port 18767 with a temporary copy of the real sample. It reads the configured Sentry DSN from the process environment or `analytics/.env`, uses environment `verification-46`, requests all four routes with identifiable trace headers, and shuts down cleanly so the SDK's normal atexit handler flushes. It prints trace ids, environment and release, never credentials. No debug/error route is added.

Executed successfully against project `kumite-analytics`, organization `university-of-maryland-ma`, release `kumite-analytics@46fefd9`. Sentry MCP confirmed these transactions and their environment/release tags:

| Route | Confirmed Sentry trace |
|---|---|
| `/learning/{session_id}` | [0dc99dcd7f634ce9a8c917a8b2d84e29](https://university-of-maryland-ma.sentry.io/explore/traces/trace/0dc99dcd7f634ce9a8c917a8b2d84e29) |
| `/trends/{player}/{character}` | [807a1f9ccce94af8bbb8b69ccc8bbfdb](https://university-of-maryland-ma.sentry.io/explore/traces/trace/807a1f9ccce94af8bbb8b69ccc8bbfdb) |
| `/stats/{session_id}` | [ae155a6e8b414ef0a11fd703fd7d3c4a](https://university-of-maryland-ma.sentry.io/explore/traces/trace/ae155a6e8b414ef0a11fd703fd7d3c4a) |

`/health` was captured by the SDK in the local transport test and returned HTTP 200 live, but its live trace `78e0ac150a4345e39895a57a6374af05` has no retained spans. Sentry's dropped-event report returned `filtered-transaction`. Sentry documents that reason as its [healthcheck/ping transaction filter](https://docs.sentry.io/api/projects/update-an-inbound-data-filter/). Thus health-check storage is filtered upstream, rather than missing SDK instrumentation. Account filter settings were not changed.

The owner accepted the existing health-check filter during remediation planning. `/health` instrumentation is verified locally; retained functional endpoint traces are the live acceptance criterion. No inbound filter was changed.

Cross-service decision spans and coach-agent monitoring are tracked separately below under B5. The analytics verification above covers analytics only.

## Remediation verification — October 17, 2026, 7:29 PM PDT

Verified working-tree changes on baseline `e876d8b`, release `kumite-analytics@e876d8b`, environment `verification-46`. The isolated transport test verifies one initialization, exactly four HTTP transactions, and `file.load`, `stats.reduce` and `learning.derive` child operations. The real analytics application was then started with its existing configured DSN, exercised and shut down normally.

Sentry MCP confirmed 15 retained spans across these requests:

| Route | Retained trace | Operation evidence |
| --- | --- | --- |
| `/learning/{session_id}` | [85a2e87cec20477d868bd9357e49ff22](https://university-of-maryland-ma.sentry.io/explore/traces/trace/85a2e87cec20477d868bd9357e49ff22) | HTTP, file loads, `learning.derive` |
| `/trends/{player}/{character}` | [51e9f084479546a8af692a4eb5fd22b8](https://university-of-maryland-ma.sentry.io/explore/traces/trace/51e9f084479546a8af692a4eb5fd22b8) | HTTP, file loads, `stats.reduce` |
| `/stats/{session_id}` | [b691a435513a4a1fae004482c2fd4077](https://university-of-maryland-ma.sentry.io/explore/traces/trace/b691a435513a4a1fae004482c2fd4077) | HTTP, `TailReader.refresh`, `stats.reduce` |

The first MCP lookup preceded full indexing; a later query confirmed all three traces and their operation spans. The dropped-event report showed two filtered spans and fifteen accepted spans in the verification interval, consistent with filtered health requests. That report is project-wide rather than proof about a particular individual health event.

Importer and database paths now emit `tigerdata.ingest`, `tigerdata.publish`, `tigerdata.read` and `tigerdata.trends` spans when they have a parent transaction. This live endpoint check used file-backed analytics; the cloud regression independently proves the database path.

**Current B5 status: analytics and replay evidence retained; brain evidence pending.** Garrett's real HTTP → agent → provider trace is verified below. [Sahil's decision trace](handoffs/sentry-brain.md), its waterfall screenshot and tracing on/off timings remain pending. The analytics and replay traces do not substitute for a game decision waterfall or prove distributed propagation across services.

M4's brain API/coach-forwarding code is now on main; Sahil reports live verification with Chloe's app. He will add brain decision spans at 5% sampling and compare hot-loop timings with tracing disabled/enabled after setting the brain DSN. Sahil reported the earlier forwarded DSN omitted its public key. On October 18 Sentry MCP retrieved the full Default client-key value again; Track D checked the public key, host and project ID and supplied the corrected value in the conversation. The value is not copied here. Local format validation is not a live ingestion test; owner configuration and org viewing access remain unverified. Source inspection at `dc1f90c` found no brain SDK initialization or decision spans. Retained brain traces, waterfall screenshot and timing results remain pending. See [the current brain handoff](handoffs/sentry-brain.md) and [return template](evidence/brain-decision-template.md). Report API readiness and observed decision frequencies do not establish mastery integration.

An October 18 live MCP [project-scoped decision-span search](https://university-of-maryland-ma.sentry.io/explore/traces/?query=span.op%3Adecision&project=4512273716281344&statsPeriod=24h) returned no results over the preceding 24 hours. This confirms no decision evidence was found by that query at inspection time; it does not diagnose why telemetry is absent. Overall B5 remains open.

**Latest owner evidence plan:** Eric confirms he has already sent the full DSN to Sahil privately, clearing the delivery blocker. Runtime configuration, instrumentation and ingestion remain unverified. The promised run uses environment **`demo-laptop`**, release equal to the full deployed `main` SHA, and a real five-operation decision transaction. Sahil will supply decision-loop p50/p95 in ms from one practice round with tracing off and one with tracing on at 5%, same settings, plus the retained trace and matching waterfall. This updates brain's expected label; it does not change historical replay/analytics environments or verify a run. His approximately 30-minute estimate follows receipt/configuration; the actual run start is not confirmed.

## B5: retained replay coach evidence — October 18, 2026

GitHub confirms both owner PRs are merged: [#15](https://github.com/ericwei1107/la-hacks-2026/pull/15) adds instrumentation (`c7e11f209460b7498dec39ea209e3740385fecc1`), and [#16](https://github.com/ericwei1107/la-hacks-2026/pull/16) records live evidence (`4787b3268d8bc086653b66b62d6039c8c899a7f0`). The authoritative owner record is [replay/SENTRY_VERIFICATION.md at the PR #16 merge](https://github.com/ericwei1107/la-hacks-2026/blob/4787b3268d8bc086653b66b62d6039c8c899a7f0/replay/SENTRY_VERIFICATION.md#retained-live-evidence-2026-10-18), read from fetched `origin/main`. That record supersedes PR #15's original pending-live-evidence wording. The trace release identifies the measured run separately from the instrumentation PR head, either merge commit, or the current deployment.

The retained [successful trace](https://university-of-maryland-ma.sentry.io/explore/traces/trace/bc9fad3bd3974dbb9145165d02f9605c/) is in `kumite-replay`, organization `university-of-maryland-ma`. Garrett ran the actual service on verification port **8776** with `KUMITE_COACH_MODE=auto`, a real HTTP `POST /coach/round` using `contracts/examples/round_summary.json`, and the real OpenAI API. Sentry MCP independently confirmed all four spans and their parent chain:

| Operation | Description | Duration |
| --- | --- | --- |
| `http.server` | `/coach/round` | 839 ms |
| `gen_ai.invoke_agent` | `round_coach` | 835 ms |
| `gen_ai.responses` | `responses gpt-4.1-nano` | 667 ms |
| `http.client` | `POST` to OpenAI Responses | 615 ms |

Project-scoped span search confirmed `coach.outcome=provider_selected` on the agent and HTTP spans, actual response model `gpt-4.1-nano-2025-04-14`, and usage of **387 input / 24 output tokens (411 total)**. All four spans carry release `kumite-replay@33d058ff7fbfe7b86a02f84e8ca24b3c2c8ff9c9` and environment `development`. This proves replay's successful provider path and retained monitoring; it does not prove demo-environment execution, live-game input, or reliable provider selection under the deadline.

### Deadline and fallback evidence

The successful run used `OPENAI_COACH_MODEL=gpt-4.1-nano` for that process only. The merged owner record reports three nano HTTP requests taking **1046, 855 and 1034 ms**, with a provider-selected tip in **1 of 3 attempts**; the other two used local fallback. The successful request's client-observed 855 ms and retained server span's 839 ms measure different intervals. `gpt-4.1-mini` took approximately **1.05–1.43 seconds** and always fell back in the owner's trial. These are small-sample owner measurements, not a reliability benchmark. The recorded source default remains `gpt-4.1-mini`; the separately requested Luna migration is not claimed implemented.

Sentry MCP independently confirmed the two supplied retained agent spans have `coach.outcome=fallback`, the same recorded release, and environment `development`:

| Trace | HTTP / agent duration | Result and owner-reported context |
| --- | --- | --- |
| [00d6272017d44356b3f2a3528afea8a4](https://university-of-maryland-ma.sentry.io/explore/traces/trace/00d6272017d44356b3f2a3528afea8a4/) | 1039 / 1035 ms | Fallback; OpenAI account had no credit and the call timed out |
| [ce7223b81fc04a5f96d800d1b7416392](https://university-of-maryland-ma.sentry.io/explore/traces/trace/ce7223b81fc04a5f96d800d1b7416392/) | 1040 / 1035 ms | Fallback; credit added, default model exceeded the deadline |

The reviewed implementation and merged evidence preserve the **1.0-second provider deadline**, with no retries and local fallback; the OpenAI client timeout is 0.9 seconds. Total HTTP duration includes surrounding work, so it may exceed the provider budget. Garrett did not extend the deadline to obtain evidence. The fallback URLs establish fallback behavior and the owner record now supplies the contexts above; they are not labelled as the two nano failures.

### Privacy and completion boundaries

Garrett reports no AI inputs/outputs, prompt text, raw session ID or round content in the retained AI attributes. The reviewed PR disables AI input/output and HTTP body capture, excludes user identity, and hashes session correlation. The inspected provider-span details expose no prompt/output content. This is scoped evidence, not a project-wide privacy audit. Garrett reports Sentry may add coarse IP-derived geography; project settings were not changed. Credentials and raw event payloads are not copied into these artifacts.

- **Replay B5 evidence complete:** retained real HTTP → agent → provider trace with outcome, actual model/usage and release/environment. Current round coaching is tool-free; no tool activity is claimed.
- **Overall B5 remains open:** Sahil must supply the real five-operation decision trace, waterfall screenshot and tracing on/off timing comparison.
- **Demo decision, October 18:** Eric approved keeping grounded local fallback and the existing one-second provider budget; Chloe agrees. Consistent OpenAI selection is not required on every tip. Chloe still verifies wording and voice timing, including fallback, on the demo host with `SENTRY_ENVIRONMENT=demo`. Eric also requested GPT-6 Luna (`gpt-6-luna`) for GPT-4 text-coaching replacements; [owner migration work](handoffs/coach-model.md) and fresh measurements remain pending. The retained nano trace remains historical B5 evidence and does not establish Luna behavior.

See [the updated replay handoff](handoffs/sentry-replay.md) for the decision and owner actions, and [the evidence index](evidence/README.md) for retained trace links.
