# Track D integration runbook

## Status and ownership

Track D can verify local files, exports, mock streams and the published report API. Native Windows/game writes, brain Sentry evidence, actual spoken timing and Chloe's UI review require their owners on the demo host. Record those as pending until the run actually happens. The proposed insights route is not available; current app/checker integrations use frozen APIs.

Use one authoritative `DATA_DIR` on Sahil's host for real recording, metadata and learning files. Tailscale access to the brain does not provide analytics access to those files. Share a working copy explicitly if services are split across hosts; verify source/session identity before interpreting freshness.

The chosen integration layout is analytics running on Sahil's Windows laptop, beside the brain, reading that same host-local folder. Chloe's app uses HTTP/WebSocket service addresses. The [example handoff](handoffs/insights-ui.md) and [published fixture index](fixtures/insights/README.md) are sufficient for her offline review while host access is arranged. Actual laptop directory, Tailscale address and remote access have been requested; no native connection or run is claimed here.

## Local reproducible check

From the repository root:

```sh
python3 tools/status/status.py
SENTRY_DSN= DATABASE_URL= .venv/bin/python -m unittest discover -s analytics/tests -v
SENTRY_DSN= DATABASE_URL= .venv/bin/python -m unittest discover -s tools/mock/tests -v
.venv/bin/python contracts/validate.py
.venv/bin/python analytics/tests/live_learning_smoke.py
```

Expect passing offline suites, a separately identified opt-in cloud skip, valid frozen examples, and two smoke PASS lines with clean shutdown. A static mock loop is playback, not proof of new completed-round writes.

Export the real evidence without cloud/model calls:

```sh
.venv/bin/python -m analytics.insights 2026-10-18T05-14-03_sahil_djin_vs_kaz --data-dir ./data/samples/live_learning --output-dir ./data/analytics
```

Expect 0/16 low blocks, 1/4 throw breaks, 0/6 estimated punish conversions, current after-block regression, absent low-defense mastery and null fine-tune results. Preserve sample files and source hashes.

## Native host launch

Use the deployed commit agreed by owners. Install analytics dependencies in the host's venv and set environment variables in the actual launch process. The brain entry point does not itself guarantee `.env` loading. Read the absolute `DATA_DIR` printed by Sahil's running brain; never substitute Eric's sample directory for a live set.

PowerShell analytics terminal, from repo root:

```powershell
$dataDir = (Resolve-Path (Read-Host 'Absolute DATA_DIR printed by the brain')).Path
$analyticsBind = Read-Host 'Laptop Tailscale IP, or 127.0.0.1 for a host-local app'
$env:DATA_DIR = $dataDir
$env:KUMITE_BRAIN_URL = 'http://127.0.0.1:8765'
$env:KUMITE_REPLAY_URL = 'http://127.0.0.1:8766'
$env:KUMITE_ANALYTICS_URL = "http://${analyticsBind}:8767"
$env:SENTRY_ENVIRONMENT = 'demo'
.\.venv\Scripts\python.exe -m analytics.demo_host serve --data-dir $dataDir --host $analyticsBind --port 8767 --file-only
```

Expect `Analytics DATA_DIR=<the same absolute folder as the brain>`, followed by Uvicorn on port 8767. The launcher requires existing `sessions/` and `recordings/`, creates no data directory, and sets `DATA_DIR` before importing analytics. `--file-only` disables database access for the first source/freshness rehearsal; cloud-backed trends remain a separate configured check. The launcher inherits Sentry settings and loads no `.env` file. Set the analytics DSN/release in this terminal when doing the separately agreed telemetry run.

On Chloe's computer, with all three services on Sahil's laptop, set these before starting/restarting Electron from `app/` (replace the host with the actual Tailscale IP/hostname):

```powershell
$demoHost = Read-Host 'Sahil laptop Tailscale IP or hostname'
$env:KUMITE_BRAIN_URL = "http://${demoHost}:8765"
$env:KUMITE_REPLAY_URL = "http://${demoHost}:8766"
$env:KUMITE_ANALYTICS_URL = "http://${demoHost}:8767"
npm run dev
```

The equivalent macOS launch from `app/` is `KUMITE_BRAIN_URL=http://HOST:8765 KUMITE_REPLAY_URL=http://HOST:8766 KUMITE_ANALYTICS_URL=http://HOST:8767 npm run dev`, substituting the agreed host. If an owner runs a service elsewhere, use that service's actual URL. Brain/replay must also be bound to reachable interfaces using their owner launch commands. Restart the app after changing addresses; the main process resolves them at startup.

Configure each service's own Sentry DSN privately; never reuse analytics/replay keys for the brain or print environment dumps. Sahil's promised brain run specifically uses `demo-laptop` and the full deployed main SHA as release; preserve that requirement rather than relabelling historical traces or forcing all projects to one label. Other service environments/releases must be recorded as actually configured.

Start Garrett's replay service with the same data directory, then Sahil's normal offline brain/game process, then Chloe's app. Use owner launch commands for their environments. Keep the approved one-second round-provider budget and local fallback. The requested Luna migration remains Garrett/Sahil's responsibility; a model-name setting alone does not establish compatible structured output or latency.

## Readiness checker handoff

Chloe's checker and its tests landed in PR #19 and are available on Eric's branch at `c87dcbe`, alongside PR #20's app work. All 15 checker tests pass locally. A [reproduced reset/late-learning false positive](evidence/pr20-integration.md) remains an owner follow-up: do not accept exit 0 alone as proof of advancement until it is corrected. The command is:

```powershell
.\.venv\Scripts\python.exe -m analytics.integration_check --session-id <actual-session-id> --watch-seconds 60 --poll-seconds 1 --timeout-seconds 2 --require-advance --json
```

Snapshot mode proves healthy responses only. Advance-required mode must compare matching stats/producer-learning round watermarks; a new active stats round alone is insufficient. Record exit 0 for satisfied requirements, 1 for unusable responses and 2 for an otherwise healthy session with no required advance. Verify a real round completion during observation, allowing recording and learning flushes to arrive separately.

## Prove the live folder is shared

In another PowerShell terminal on Sahil's laptop, use the same absolute folder and actual analytics bind address from the launch terminal:

```powershell
$dataDir = (Resolve-Path (Read-Host 'Absolute DATA_DIR printed by the brain')).Path
$sessionId = Read-Host 'Current real session id from the brain'
$analyticsHost = Read-Host 'Analytics bind IP used by the launch terminal'
.\.venv\Scripts\python.exe -m analytics.demo_host check --data-dir $dataDir --session-id $sessionId --brain-url http://127.0.0.1:8765 --analytics-url "http://${analyticsHost}:8767"
```

The check makes only GET requests. It compares the brain's immutable session identity and complete recording-prefix hash with the local canonical files, then compares remote stats and learning with the local file-backed reducer. It rechecks source identity after HTTP reads and retries a changing capture once. A stale copy with the same session id can therefore fail even if `/health` is healthy. No raw recording or credentials appear in the result.

Exit 0 means matched source/API snapshots with completed learning current; exit 1 means a mismatch, malformed/unavailable data or repeated source change; exit 2 means matched usable sources whose completed learning is still pending. The report includes current completed/pending round lists, version strings, local/brain prefix hashes and a pending recording-tail flag. It does not prove future writes, remote-app reachability, voice timing or native shutdown behavior. During continuous writes, retry an unavailable/changing snapshot after the next flush.

Retain this result before and after a real completed round, alongside the C1 watcher output. Require the later common completed round in both local/HTTP sources and no reset used as advancement. The current C1 reset caveat still applies; a watcher exit 0 alone is insufficient. Verify Chloe's selected live session and visible Stats/Learning converge after the actual files arrive, then record the observed delay.

Local automated rehearsal:

```sh
SENTRY_DSN= DATABASE_URL= .venv/bin/python analytics/tests/demo_host_smoke.py
```

This starts the actual brain and analytics HTTP implementations on temporary ports, using a temporary copy of the real fixture. Scripted additions exercise partial recording tails, a later completed round, delayed learning and wrong-folder content. Expect two PASS lines and clean test-process shutdown, with original fixture hashes unchanged. Scripted additions are test data; this is not a Windows/game/native app observation.

## Host acceptance observations

| Check | Required observation | Current status |
| --- | --- | --- |
| Identity | Three health service identities; same real session in stats/learning | Native host pending |
| Round advance | A later completed round reaches both stats and learning | Native host pending |
| Delayed learning | Pending state catches up; no fabricated zero | Chloe/native host pending |
| Reconnect/session change | Reconnection refetches authoritative data; late responses cannot cross sessions | Chloe/native host pending |
| Ports/shutdown | Occupied port is handled; Ctrl-C releases processes/pad safely | Native host pending |
| Database unavailable | Local stats/learning and file-backed trends stay usable | Native host pending; prior local regression retained |
| Audio | Provider and local fallback tips are grounded and spoken promptly | Chloe/native host pending |
| Display | Counts/status and selected session are readable at 1080p | Chloe's [static real-fixture review](../app/docs/acceptance/2026-10-18-stats-learning.md) retained; demo-host review pending |
| Brain telemetry | Matching trace/waterfall, sampling config and on/off timing accepted | Sahil evidence pending |

Only stop test processes you started. Do not kill owner-run services or alter live configuration to manufacture a passing result. Record machine/OS/Python/deployed commit, command, source session, observation period and exact result for each check.

## Report API

Use the real service for `POST /analyze/{session_id}` then `GET /reports/{session_id}` against a temporary copy of the synthetic fixture and real M3 fixture. Validate the report schema, saved GET equality and citations against original line/round/frame. With external keys disabled, require honest unscored/fallback labels, not fabricated model scores. Local response validity does not prove real Jev/provider activity. See `handoffs/report-integration.md`.

## B5 return and acceptance

Use `evidence/brain-decision-template.md`. Verify real read/decode/reflex/tactical/input parentage, transaction lifetime before the generator read, matching screenshot, actual full release and `demo-laptop`, plus 5% deployed sampling configuration. One retained trace does not measure sampling frequency.

Retain one comparable practice round off/on with p50/p95 decision-loop milliseconds, durations and sample counts. Preserve transport-unavailable/kill-switch/pad-release observations separately. Sahil owns acceptable-overhead judgment; no invented threshold or general reliability claim is allowed. Keep overall B5 open until owner artifacts are received and checked.

## Performance and publication

```sh
.venv/bin/python -m analytics.benchmark_insights 2026-10-18T05-14-03_sahil_djin_vs_kaz --data-dir ./data/samples/live_learning
```

This prints twenty cached internal captures, p50/p95/max, machine/Python, source snapshot, base commit and implementation hashes. It does not measure HTTP or native gameplay. With replay dependencies installed in the selected Python environment, `python analytics/tests/report_smoke.py` checks the actual replay HTTP service against temporary copies of both fixtures with provider/model calls disabled.

Measure cached insight derivation on representative sources; 250 ms p95 is the current engineering target. Measure visible completed-round updates after required files become available; two seconds is the display target. These require reported measurements, not assertions inferred from local unit tests.

Keep the insight format/definition versions separate from persisted calculation version 4. A future stored-semantic correction needs a version bump, approved scoped backfill, aggregate/file parity and immediate zero-import repeat. No new cloud write is needed for this implementation's internal export.

Before release, run team status, owner review and `/handoff` for reviewed named paths. Keep credentials, generated exports and prep local. The submission ledger distinguishes implemented, locally verified, native-host verified, pending and deferred work.
