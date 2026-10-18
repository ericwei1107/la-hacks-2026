# Sentry for the brain (from Eric)

Project: `kumite-brain` in Sentry org `university-of-maryland-ma`.

M4's API/coach-forwarding code is on main; Sahil reports it was verified live with Chloe's app. The next owner task is brain Sentry at 5% sampling plus tracing on/off timing comparison. Sentry MCP verified the existing `kumite-brain` DSN for Eric to forward privately; org viewing access remains unverified. See [current handoff](../../../analytics/handoffs/sentry-brain.md). The real summary/learning sample's local/cloud intake is already verified in [B4](../../../analytics/LIVE_LEARNING_VERIFICATION.md).

## 1. Get the DSN (never commit it)

If you're a member of the Sentry org and your Claude Code has the Sentry MCP, ask your agent to look it up: `find_dsns` for org `university-of-maryland-ma`, project `kumite-brain`. Otherwise ask Eric. Put it in a gitignored `.env`:

```
SENTRY_DSN=<the kumite-brain DSN>
SENTRY_ENVIRONMENT=development
```

## 2. Install and initialize

`pip install "sentry-sdk[fastapi]>=2.35"`, then at the top of the brain's entry module, before `app = FastAPI()`:

```python
import os, subprocess, sentry_sdk
sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    environment=os.environ.get("SENTRY_ENVIRONMENT", "development"),
    release="kumite-brain@" + subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip(),
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

Use the agreed 5% root sampling rate. Start the sampled decision context before the actual read and finish it after input; follow the [location and context-lifetime handoff](../../../analytics/handoffs/sentry-brain.md). Keep transport work off the hot loop and measure the instrumentation overhead with tracing disabled/enabled. Sampling alone does not establish acceptable timing.

## 4. At the demo

Set `SENTRY_ENVIRONMENT=demo` on the demo laptop for every service, so demo errors are separate from development noise.

`/team-status` reports source matches as `on_branch` or `on_main`. Those signals do not verify runtime sampling, actual pipeline spans or acceptable overhead. The separate manual `sentry-brain-evidence` item requires a retained trace URL, waterfall screenshot and on/off timings; the owner's commitment alone does not close it.
