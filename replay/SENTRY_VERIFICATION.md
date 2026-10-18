# Replay coach trace verification

Project: `kumite-replay`, organization: `university-of-maryland-ma`.

The SDK initializes once, after the repository .env loads and before FastAPI
construction. Set SENTRY_DSN to the project's Client Keys (DSN) value, not its
browser URL. Without a valid DSN, coaching works but telemetry is disabled.
SENTRY_RELEASE defaults to `kumite-replay@<full Git commit>`; an explicit value
overrides it. SENTRY_ENVIRONMENT defaults to `development`; use `demo` on the demo
laptop or a distinct verification environment for the evidence run.

Round requests retain their HTTP transaction. The `round_coach` child uses
`gen_ai.invoke_agent`; Sentry owns the actual `gen_ai.responses` provider span.
Responses.create uses the same strict tip-selection schema and local validation
as the former Responses.parse path, which the SDK does not instrument.
AI spans are included in the parent transaction envelope rather than streamed
separately. No second exporter or fabricated provider spans are added.

The agent's `coach.outcome` attribute and the HTTP transaction's matching tag are:

| Value | Meaning |
| --- | --- |
| provider_selected | Provider returned an allowed, validated tip |
| fallback | A provider was attempted but failed, timed out or returned invalid output |
| deterministic | One grounded tip was sufficient, so no provider was called |
| local | No provider was configured |

Only provider_selected with actual provider activity proves the successful model
path. HTTP 200 alone does not. The one-second provider deadline, no retries,
20-word limit and deterministic fallback remain in force.

Prompts, outputs, HTTP bodies/headers/cookies/query parameters, player identity and
stack variables are excluded. Correlation uses a SHA-256 session identifier.
Session path segments in report/analyze/learning URLs are normalized. Raw OpenAI
exception events are dropped because provider errors can echo submitted data;
the provider span and fallback outcome still record the failure. These controls
apply to telemetry, not the actual OpenAI request, which still receives the
round summary for tip selection.

## Run and capture real evidence

Configure the ignored root .env with OPENAI_API_KEY, the replay project's
SENTRY_DSN, and SENTRY_ENVIRONMENT. Do not paste credentials into chat or commit
them. SENTRY_AUTH_TOKEN is not required to send traces; viewing retained traces
requires project access through Sentry or an appropriately scoped read token.

From the repository root:

```powershell
.\replay\.venv\Scripts\python.exe -m pip install -r replay/requirements.txt
$env:KUMITE_COACH_MODE = 'auto'
.\replay\.venv\Scripts\python.exe -m uvicorn replay.main:app --host 127.0.0.1 --port 8766
```

In a second terminal:

```powershell
$response = Invoke-WebRequest -Method Post -Uri http://127.0.0.1:8766/coach/round -ContentType 'application/json' -InFile contracts/examples/round_summary.json
$response.Content
$response.Headers['X-Sentry-Trace-Id']
```

This public contract example offers two grounded tips, allowing the optional
provider path. Fixed habits or uniquely grounded named-move tips can legitimately
skip OpenAI. Do not modify real recording evidence to force a model call or
increase the production timeout for verification.

Find the returned trace ID in the replay Sentry project. Confirm the retained
HTTP → agent → provider hierarchy, provider_selected, actual model/token usage,
release and environment. Copy its direct trace URL from Sentry and send it with
the branch/PR, release and environment to Eric. A generated trace ID or local
envelope is not proof of ingestion; do not label it retained until confirmed.

## Current validation

The offline suite captures envelopes from actual HTTP handlers and the real
OpenAI SDK using a mocked provider transport. It verifies parentage, model/usage,
release/environment, privacy, local/deterministic paths, provider errors,
invalid selections, timeouts and malformed-DSN fallback. All automated tests
disable external Sentry upload, including during test collection.

```powershell
.\replay\.venv\Scripts\python.exe -m pytest replay/tests -q
.\replay\.venv\Scripts\python.exe contracts/validate.py
```

Expected: 212 tests pass and the contract validator prints PASS. Live OpenAI and
retained Sentry evidence remain a separate check; no retained URL has been
verified for this change yet.
