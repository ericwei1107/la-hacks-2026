# Sentry for the replay service (from Eric)

Project: `kumite-replay` in Sentry org `university-of-maryland-ma`.

## 1. Get the DSN (never commit it)

If you're a member of the Sentry org and your Claude Code has the Sentry MCP, ask your agent to look it up: `find_dsns` for org `university-of-maryland-ma`, project `kumite-replay`. Otherwise ask Eric. Put it in a gitignored `.env`:

```
SENTRY_DSN=<the kumite-replay DSN>
SENTRY_ENVIRONMENT=development
```

## 2. Install and initialize

`pip install "sentry-sdk[fastapi]>=2.35"`, then at the top of the service's entry module, before `app = FastAPI()`:

```python
import os, subprocess, sentry_sdk
sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    environment=os.environ.get("SENTRY_ENVIRONMENT", "development"),
    release="kumite-replay@" + subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip(),
    traces_sample_rate=1.0,
    enable_logs=True,
    send_default_pii=True,
)
```

## 3. Agent monitoring for the coach

OpenAI and Anthropic SDK calls, including tool calls, are recorded automatically. Wrap each coach-agent run so a whole turn shows as one trace:

```python
with sentry_sdk.start_transaction(op="gen_ai.invoke_agent", name="coach_agent"):
    ...
```

Tracing plus agent monitoring is what the Sentry challenge asks for.

## 4. At the demo

`SENTRY_ENVIRONMENT=demo` on the demo laptop.

`/team-status` closes these items automatically once `sentry_sdk.init`, `gen_ai.invoke_agent` and `SENTRY_ENVIRONMENT` appear in `replay/` on any branch.
