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

Cross-service decision spans and coach-agent monitoring remain section 6.2 work. This verification does not claim they are configured.

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

**Cross-track sponsor status: blocked on retained owner decision and coach traces.** Concrete handoffs are [Sahil](handoffs/sentry-brain.md) and [Garrett](handoffs/sentry-replay.md). Their required decision-waterfall screenshot remains pending because there is no retained game decision trace to capture. Trace URLs above are analytics evidence, not substitutes for that screenshot.
