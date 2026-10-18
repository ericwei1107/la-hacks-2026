# Garrett: retained coach-agent monitoring

Owner: Track C. Project: `kumite-replay`; org: `university-of-maryland-ma`. Track D has not edited `replay/`.

Inspected `origin/garrett/characters` commit `e85dcbd`: `replay.main.create_app`, its `/coach/round` handler, `replay.coach.RoundCoach.coach`, and `OpenAIProvider.__call__`. The provider calls `AsyncOpenAI.responses.parse`; the local fallback is deterministic and makes no model call. This code is on the owner branch rather than the local main baseline.

Initialize Sentry once before constructing the FastAPI app; use the project DSN, release and `SENTRY_ENVIRONMENT` from the process environment. Preserve the five-second provider deadline and local fallback. Use the Sentry SDK as the one AI instrumentation owner; do not add a second exporter or duplicate provider spans.

Follow [Python Agent Tracing](https://docs.sentry.io/platforms/python/agent-tracing/) and [the OpenAI integration](https://docs.sentry.io/platforms/python/agent-tracing/openai/) for the installed SDK. Verify that the actual Responses call is captured; a generic agent wrapper alone is insufficient.

- Wrap a real `RoundCoach.coach` invocation in `gen_ai.invoke_agent` while retaining the parent HTTP context. Use a child span when the HTTP transaction already exists.
- Keep automatic OpenAI provider instrumentation enabled. Record the actual model, request/response and reported usage using SDK conventions.
- Attach a stable opaque session/conversation identifier. For future tools such as `get_learning_curve`, instrument the real call to `KUMITE_ANALYTICS_URL/learning/<session_id>`; do not fabricate tool spans for today's tool-free round coach.
- Label fallback runs accurately. A deterministic fallback without a provider call is not model-monitoring evidence.

## Acceptance

Run a contract-valid round summary through the real service with a configured provider. Confirm a retained HTTP → agent → provider trace, readable actual model activity and release/environment tags. Retain tool activity once a tool-enabled coach exists. Save the direct trace URL alongside the decision-waterfall evidence in `analytics/SENTRY_VERIFICATION.md`.

Re-test missing key, provider timeout and unavailable network: coaching must still return the local fallback within the existing API deadline. Keep credentials out of examples and artifacts. Cross-service sponsor completion remains blocked until retained owner evidence exists.
