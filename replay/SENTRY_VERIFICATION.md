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

Expected: 212 tests pass and the contract validator prints PASS.

## Retained live evidence (2026-10-18)

Code verified: commit `33d058ff7fbfe7b86a02f84e8ca24b3c2c8ff9c9`, run as the
actual service on port 8776 with `KUMITE_COACH_MODE=auto`, environment
`development`, and `OPENAI_COACH_MODEL=gpt-4.1-nano` set for that process only.
The request was a real HTTP `POST /coach/round` of
`contracts/examples/round_summary.json`.

Retained trace `bc9fad3bd3974dbb9145165d02f9605c`, opened in Sentry by Garrett:
https://university-of-maryland-ma.sentry.io/explore/traces/trace/bc9fad3bd3974dbb9145165d02f9605c/

| Check | Observed |
| --- | --- |
| Hierarchy | `http.server /coach/round` 839 ms, `gen_ai.invoke_agent round_coach` 835 ms, `gen_ai.responses` 667 ms, `http.client POST api.openai.com/v1/responses` 615 ms |
| Outcome | `coach.outcome` = `provider_selected` |
| Model and usage | `gpt-4.1-nano-2025-04-14`, 387 input and 24 output tokens, 411 total, operation `responses`, provider `openai` |
| Release and environment | `kumite-replay@33d058ff7fbfe7b86a02f84e8ca24b3c2c8ff9c9`, `development` |
| Project | The DSN used ends in the same project ID as the Client Keys page of `kumite-replay` |
| Content | Input and Output tabs of the AI span are empty; attributes list only operation, model, token, cost, release, environment, SDK and ID fields |

Sentry adds a coarse `user.geo` from the sender's IP address at ingestion. It is
not collected by the SDK and can be disabled in the project's IP storage setting.

Two earlier traces from the same code show the fallback path and are not
evidence of provider selection: `00d6272017d44356b3f2a3528afea8a4` (the OpenAI
account had no credit; the call hit the timeout) and `ce7223b81fc04a5f96d800d1b7416392` (credit added; the
default model was slower than the deadline).

### Latency finding

The one-second deadline and 0.9-second SDK timeout were not changed. Measured
against the real API from the verification machine:

| Model | Result against the deadline |
| --- | --- |
| `gpt-4.1-mini` (default) | 1.05 to 1.43 s per call; exceeds the deadline, so requests fall back to the grounded local tip |
| `gpt-4.1-nano` | Three HTTP requests took 1046, 855 and 1034 ms; one finished inside the deadline and selected a provider tip, the other two fell back |

Eric told Garrett that the local fallback is acceptable. The default model
therefore usually returns the deterministic grounded tip; set
`OPENAI_COACH_MODEL` to change that. Fallback is always safe because every
returned tip is one of the grounded, move-validated candidates.
