# Sentry for the brain (from Eric)

Project: `kumite-brain` in Sentry org `university-of-maryland-ma`.

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
    traces_sample_rate=1.0,
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

Trace only decision points, or sample about 5% of them, so the quota lasts at 60 decisions per second. The SDK sends from a background thread and never blocks the hot loop.

## 4. At the demo

Set `SENTRY_ENVIRONMENT=demo` on the demo laptop for every service, so demo errors are separate from development noise.

`/team-status` closes these items automatically once `sentry_sdk.init`, `op="decision"` and `SENTRY_ENVIRONMENT` appear in `game/` on any branch.
