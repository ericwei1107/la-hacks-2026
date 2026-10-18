# Track D integration runbook

## Status and ownership

Track D can verify local files, exports, mock streams and the published report API. Native Windows/game writes, brain Sentry evidence, actual spoken timing and Chloe's UI review require their owners on the demo host. Record those as pending until the run actually happens. The proposed insights route exists only behind `KUMITE_EXPERIMENTAL_INSIGHTS=1` (real) or `--experimental-insights` (mock) and is not agreed; current app/checker integrations use frozen APIs.

Use one authoritative `DATA_DIR` on Sahil's host for real recording, metadata and learning files. Tailscale access to the brain does not provide analytics access to those files. Share a working copy explicitly if services are split across hosts; verify source/session identity before interpreting freshness.

**Demo host, confirmed by Sahil on October 18:** brain, replay and analytics all run on his Windows laptop and share `DATA_DIR=C:\Users\sahil\la-hacks-2026\data`. There is no remote execution on the demo machine before the demo. Eric does not run commands there: Sahil runs the source check below against a live session and pastes its JSON output, and Eric verifies it. No Tailscale address is needed for the source check because every service it calls is on the same laptop. The [example handoff](handoffs/insights-ui.md) and [published fixture index](fixtures/insights/README.md) remain sufficient for Chloe's offline review. No native run is claimed until the pasted output is checked. Sahil reviewed PRs #22 and #25 from the Track A side (no objection) and will check out the commit Eric names for the demo API; he runs the source check in the demo session, which starts after the punish rollout window closes.

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

Rehearse a growing session and the opt-in insights route without the game, in two terminals:

```sh
DATA_DIR=./data/samples/live_learning SENTRY_DSN= .venv/bin/python tools/mock/serve.py --services brain,replay --live-dir /tmp/kumite-live --learning-delay 3
DATA_DIR=/tmp/kumite-live KUMITE_EXPERIMENTAL_INSIGHTS=1 DATABASE_URL= SENTRY_DSN= .venv/bin/python -m uvicorn analytics.main:app --port 8767
```

Expect each round to show pending learning for about three seconds after its summary, then current, ending at 0/16 lows. This is scripted playback of a recorded set, not a native observation; see the [mock README](../tools/mock/README.md#live-refresh-scenario) for reconnect and duplicate-summary options.

Export the real evidence without cloud/model calls:

```sh
.venv/bin/python -m analytics.insights 2026-10-18T05-14-03_sahil_djin_vs_kaz --data-dir ./data/samples/live_learning --output-dir ./data/analytics
```

Expect 0/16 low blocks, 1/4 throw breaks, 0/6 estimated punish conversions, current after-block regression, absent low-defense mastery and null fine-tune results. Preserve sample files and source hashes.

## Native host launch

Use the deployed commit agreed by owners. Sahil keeps his existing launch commands for brain, replay and analytics on the laptop, all with the same folder. If analytics is restarted, the launcher below validates that folder before importing analytics and loads no `.env` file:

```powershell
cd C:\Users\sahil\la-hacks-2026
$env:SENTRY_ENVIRONMENT = 'demo'
.\.venv\Scripts\python.exe -m analytics.demo_host serve --data-dir C:\Users\sahil\la-hacks-2026\data --host 127.0.0.1 --port 8767 --file-only
```

Expect `Analytics DATA_DIR=C:\Users\sahil\la-hacks-2026\data`, followed by Uvicorn on port 8767. `demo_host` exists only on the PR #22 branch until it merges; until then, keep the existing analytics launch command with `DATA_DIR` set to the same folder. `--file-only` disables database access; cloud-backed trends remain a separate configured check. The brain entry point does not itself guarantee `.env` loading, so set Sentry variables in the launch terminal.

Chloe's app runs on the laptop too (confirmed by Sahil), so every service address stays `127.0.0.1`.

```powershell
$demoHost = '127.0.0.1'
$env:KUMITE_BRAIN_URL = "http://${demoHost}:8765"
$env:KUMITE_REPLAY_URL = "http://${demoHost}:8766"
$env:KUMITE_ANALYTICS_URL = "http://${demoHost}:8767"
npm run dev
```

Restart the app after changing addresses; the main process resolves them at startup.

Configure each service's own Sentry DSN privately; never reuse analytics/replay keys for the brain or print environment dumps. Sahil's brain run uses `demo-laptop` and the full deployed main SHA as release; other service environments/releases must be recorded as actually configured.

Start Garrett's replay service with the same data directory, then Sahil's normal offline brain/game process, then Chloe's app. Use owner launch commands for their environments. Keep the approved one-second round-provider budget and local fallback. The requested Luna migration remains Garrett/Sahil's responsibility; a model-name setting alone does not establish compatible structured output or latency.

## Readiness checker handoff

Chloe's checker and its tests landed in PR #19 and are available on Eric's branch at `c87dcbe`, alongside PR #20's app work. All 15 checker tests pass locally. A [reproduced reset/late-learning false positive](evidence/pr20-integration.md) remains an owner follow-up: do not accept exit 0 alone as proof of advancement until it is corrected. The command is:

```powershell
.\.venv\Scripts\python.exe -m analytics.integration_check --session-id <actual-session-id> --watch-seconds 60 --poll-seconds 1 --timeout-seconds 2 --require-advance --json
```

Snapshot mode proves healthy responses only. Advance-required mode must compare matching stats/producer-learning round watermarks; a new active stats round alone is insufficient. Record exit 0 for satisfied requirements, 1 for unusable responses and 2 for an otherwise healthy session with no required advance. Verify a real round completion during observation, allowing recording and learning flushes to arrive separately.

## Prove the live folder is shared (Sahil runs, pastes output)

Sahil runs this on the laptop in a new PowerShell window while a real session is being played. It reads the checker from the PR #22 branch in a separate, detached worktree, so the deployed checkout's files and branch are not changed. It uses the laptop's existing virtual environment and makes only GET requests to the local brain and analytics.

```powershell
cd C:\Users\sahil\la-hacks-2026
git fetch origin track-d-insights-host-handoff
git worktree add --detach ..\kumite-source-check FETCH_HEAD
cd ..\kumite-source-check
$out = & C:\Users\sahil\la-hacks-2026\.venv\Scripts\python.exe -m analytics.demo_host check --data-dir C:\Users\sahil\la-hacks-2026\data --session-id latest --wait-for-round-seconds 300
$code = $LASTEXITCODE
$out | Set-Clipboard
$out
"exit $code"
```

Start it during a round or just before one. It checks the newest session in `DATA_DIR/sessions`, which is the brain's newest-first ordering, then waits up to five minutes for the next completed round whose learning has been saved, and checks again. The JSON is copied to the clipboard; paste all of it plus the `exit` line. It contains the folder path, session id, round lists, service versions and SHA-256 hashes, and no credentials or recording content.

| Exit | Meaning | Next step |
| --- | --- | --- |
| 0 | Brain recording prefix, analytics stats and learning match the local files before and after a later completed round | Paste output; Eric records the native source proof |
| 2 | Sources match, but no new round completed with its learning saved within the wait | Play a round and rerun; paste the output anyway |
| 1 | Mismatch, unavailable service or repeatedly rewritten source | Paste output; do not change services to make it pass |

If analytics is not on `127.0.0.1:8767`, add `--analytics-url http://<address>:8767`. If `python` reports a missing module, run `C:\Users\sahil\la-hacks-2026\.venv\Scripts\python.exe -m pip install -r analytics\requirements.txt` from the worktree, then rerun. Remove the worktree afterwards with `cd C:\Users\sahil\la-hacks-2026; git worktree remove ..\kumite-source-check`.

How it compares: the brain's recording bytes must match the local file's complete-line prefix. If no file changes during the check, remote stats and learning must equal the local reducer exactly (`"comparison": "exact"`). If the recording or learning grows during the check, which is normal mid-round, the earlier bytes must be unchanged and only completed rounds are compared: stats rounds that are closed, and learning rounds that are closed and already saved (`"comparison": "completed_rounds_while_appending"`). Metadata `recording` values relative to the brain's working directory resolve to `DATA_DIR/recordings/<session_id>.jsonl`. The check does not prove remote-app reachability, voice timing or native shutdown behavior.

Retain the pasted result alongside the C1 watcher output. The C1 reset caveat still applies; a watcher exit 0 alone is insufficient. Verify Chloe's selected live session and visible Stats/Learning converge after the files arrive, then record the observed delay.

Local automated rehearsal:

```sh
SENTRY_DSN= DATABASE_URL= .venv/bin/python analytics/tests/demo_host_smoke.py
```

This starts the actual brain and analytics HTTP implementations on temporary ports, using a temporary copy of the real fixture with recorder-style relative metadata. Scripted additions exercise partial recording tails, a later completed round, delayed learning, the one-command before/after capture with `--session-id latest`, a check during continuous writes and wrong-folder content. Expect two PASS lines and clean test-process shutdown, with original fixture hashes unchanged. Scripted additions are test data; this is not a Windows/game/native app observation.

## Host acceptance observations

| Check | Required observation | Current status |
| --- | --- | --- |
| Identity | Three health service identities; same real session in stats/learning | Command sent to Sahil; awaiting pasted `demo_host check` output |
| Round advance | A later completed round reaches both stats and learning | Same command (`--wait-for-round-seconds 300`); awaiting pasted output |
| Delayed learning | Pending state catches up; no fabricated zero | Chloe/native host pending |
| Reconnect/session change | Reconnection refetches authoritative data; late responses cannot cross sessions | Chloe/native host pending |
| Ports/shutdown | Occupied port is handled; Ctrl-C releases processes/pad safely | Native host pending |
| Database unavailable | Local stats/learning and file-backed trends stay usable | Native host pending; prior local regression retained |
| Audio | Provider and local fallback tips are grounded and spoken promptly | Chloe/native host pending |
| Display | Counts/status and selected session are readable at 1080p | Chloe's [static real-fixture review](../app/docs/acceptance/2026-10-18-stats-learning.md) retained; demo-host review pending |
| Brain telemetry | Matching trace/waterfall, sampling config and on/off timing accepted | Sahil instrumenting now; trace URL, waterfall, full SHA release, `demo-laptop`, on/off p50/p95 with sample counts promised within the hour of 03:40 PT, October 18 |

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
