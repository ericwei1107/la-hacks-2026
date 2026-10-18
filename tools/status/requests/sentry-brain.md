# Sentry for the brain (from Eric)

Project: `kumite-brain` in Sentry org `university-of-maryland-ma`.

M4's API/coach-forwarding code is on main; Sahil reports it was verified live with Chloe's app. The next owner task is brain Sentry at 5% sampling plus tracing on/off timing comparison. The first forwarded DSN was incomplete. Sentry MCP has retrieved the full Default client-key DSN again, including its public key, for Eric to forward privately; owner configuration, ingestion and org viewing access remain unverified. See [current handoff](../../../analytics/handoffs/sentry-brain.md). The real summary/learning sample's local/cloud intake is already verified in [B4](../../../analytics/LIVE_LEARNING_VERIFICATION.md).

## 1. Get the DSN (never commit it)

Copy the full DSN from [kumite-brain → Project Settings → Client Keys](https://university-of-maryland-ma.sentry.io/settings/projects/kumite-brain/keys/) or use Sentry MCP `find_dsns` for org `university-of-maryland-ma`, project `kumite-brain`. Otherwise ask Eric. The value must include the public key before `@`; the host and project number alone are incomplete:

```
SENTRY_DSN=https://<public-key>@o4512273697341440.ingest.us.sentry.io/4512273716281344
SENTRY_ENVIRONMENT=demo-laptop
SENTRY_RELEASE=<full-deployed-main-sha>
```

The above is a shape example, not a usable credential. Keep the real value out of tracked files. A gitignored `.env` is storage only: the inspected `game.bot` entry point does not load it automatically. Set variables in the same process environment that launches the bot, or use an explicitly configured owner launcher.

Eric confirms he has already sent the complete value to Sahil by **private DM**. Delivery is complete by owner report; no duplicate send is needed. Process configuration and runtime evidence remain pending. Do not copy the value into the tracker or a shared handoff.

Sahil's instrumentation landed on main as `e8f134f`. Trace, release, environment, sampling and off/on timings were received and the trace was verified by Track D on October 18 ([record](../../../analytics/evidence/brain-decision-2026-10-18.md)). The screenshot is retained and Sahil accepted the overhead provided timing is unaffected (identical missed-frame counts off and on). Complete.

For PowerShell, from the repo root (replace the placeholder privately):

```powershell
$env:SENTRY_DSN = '<paste the complete brain DSN>'
$env:SENTRY_ENVIRONMENT = 'demo-laptop'
$env:SENTRY_RELEASE = (git rev-parse HEAD).Trim()
.\.venv\Scripts\python.exe -m pip install "sentry-sdk[fastapi]>=2.35"
.\.venv\Scripts\python.exe -c "import os; from sentry_sdk.utils import Dsn; d = Dsn(os.environ['SENTRY_DSN']); assert d.public_key and d.host == 'o4512273697341440.ingest.us.sentry.io' and d.project_id == '4512273716281344'; print('PASS: complete kumite-brain DSN in this process environment')"
```

Expect the PASS line without a key being printed. A malformed/incomplete value must fail. This checks local configuration only, sends no event and does not prove SDK initialization or live ingestion. Run from the deployed `main` checkout so `SENTRY_RELEASE` is the full SHA actually executed. Once the owner instrumentation below is implemented, launch the normal game command from this same terminal.

## 2. Install and initialize

Sahil owns dependency and source changes in `game/`. Persist the SDK dependency in the owner's requirements and initialize it once in the game entry process, before the API thread and hot loop start. Initializing only a separately launched API process will not instrument the bot loop. Preserve existing initialization if an owner branch already adds it:

```python
import os, subprocess, sentry_sdk
sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    environment=os.environ.get("SENTRY_ENVIRONMENT", "development"),
    release=os.environ.get("SENTRY_RELEASE") or subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip(),
    traces_sample_rate=0.05,
    enable_logs=True,
)
```

## 3. One span per decision (a demo slide)

```python
with sentry_sdk.start_transaction(op="decision", name="decision"):
    with sentry_sdk.start_span(op="read"): ...
    with sentry_sdk.start_span(op="decode"): ...
    with sentry_sdk.start_span(op="reflex"): ...
    with sentry_sdk.start_span(op="tactical"): ...
    with sentry_sdk.start_span(op="input"): ...
```

The nesting above illustrates span relationships; replace ellipses with the actual operations at their owner entry points. Use the agreed 5% root sampling rate. Start the sampled decision context before the actual read and finish it after input; follow the [location and context-lifetime handoff](../../../analytics/handoffs/sentry-brain.md). Keep transport work off the hot loop and measure the instrumentation overhead with tracing disabled/enabled. Sampling alone does not establish acceptable timing.

## 4. At the demo

For the promised brain run, set `SENTRY_ENVIRONMENT=demo-laptop` and release equal to the full deployed `main` SHA. This replaces the earlier generic `demo` instruction for brain only. Verify each other service's actual configured environment independently; do not relabel historical replay/analytics evidence.

Sahil will return the decision trace URL with real read/decode/reflex/tactical/input spans, deployed SHA, environment, and decision-loop p50/p95 in ms from one practice round each way with identical settings and tracing on at 5%. Retain the matching waterfall screenshot as already requested. About 30 minutes after private delivery/configuration is his estimate, not a verification result.

`/team-status` reports source matches as `on_branch` or `on_main`. Those signals do not verify runtime sampling, actual pipeline spans or acceptable overhead. The separate manual `sentry-brain-evidence` item requires a retained trace URL, waterfall screenshot and on/off timings; the owner's commitment alone does not close it.

Return the [evidence template](../../../analytics/evidence/brain-decision-template.md) with the owner commit/PR, release/environment, retained URL, matching screenshot and comparable timing results. Keep this item open until Track D checks the actual trace and Sahil accepts the measured overhead.
