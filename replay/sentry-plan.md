# Replay Sentry evidence implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Produce a real HTTP → coach agent → OpenAI Responses trace with explicit outcomes and release/environment attribution.

**Architecture:** Initialize the Sentry SDK once after loading local environment settings and before constructing FastAPI. Keep the HTTP transaction as the parent and instrument round coaching with a child agent span. Let Sentry's OpenAI integration own provider spans, including Responses.parse; never synthesize successful provider evidence.

**Tech stack:** Existing FastAPI/OpenAI SDK, pinned sentry-sdk and urllib3.

**Spec:** tools/status/requests/sentry-replay.md and origin/main:analytics/handoffs/sentry-replay.md.

## Constraints

- Edit replay/ only; do not edit Claude's character_data.py, options.py, or test_options.py.
- Preserve the current one-second round provider deadline, 20-word output and deterministic fallback.
- Keep credentials, prompts, raw recordings and player identifiers out of telemetry artifacts. Use a hashed session identifier for correlation.
- A local captured envelope is preparation, not a retained Sentry trace. Confirm actual ingestion before claiming B5 evidence.

## Review focus

- Responses.parse must produce a real SDK provider span, rather than an agent-only trace.
- Provider timeouts/errors/invalid selections must remain distinguishable from provider-selected tips.
- Deterministic and missing-key runs must not pretend to invoke OpenAI.
- Request contents, authorization and model messages must not leak through telemetry.
- Repeated app creation and absent DSN must not reset an existing client or send telemetry accidentally.

## Tasks

- [x] Add failing envelope-capture integration tests for HTTP/agent/provider parentage, release/environment, usage and privacy, plus fallback paths.
- [x] Pin/install dependencies and implement optional Sentry initialization, child agent spans and truthful outcome tags.
- [x] Verify the replay suite and frozen contract validation; obtain an independent review.
- [ ] Document exact run/evidence commands, commit replay changes and publish a clean branch/PR.
- [ ] With a locally configured replay DSN and org access, run the public contract example against the real HTTP service and OpenAI. Confirm retained trace content before sharing its URL. Otherwise report the precise access/configuration blocker.
