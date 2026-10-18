# Sentry for the replay service (from Eric)

Project: `kumite-replay` in Sentry org `university-of-maryland-ma`.

## Current status — October 18, 2026

[PR #15](https://github.com/ericwei1107/la-hacks-2026/pull/15) and [PR #16](https://github.com/ericwei1107/la-hacks-2026/pull/16) are merged. The latter publishes the retained evidence in `replay/SENTRY_VERIFICATION.md`. Replay B5 evidence is accepted: a retained real `/coach/round` HTTP → `gen_ai.invoke_agent` → OpenAI `gen_ai.responses` trace has `provider_selected`, actual model/token usage and release/environment. See [the verification record](../../../analytics/SENTRY_VERIFICATION.md#b5-retained-replay-coach-evidence--october-18-2026) and [owner handoff](../../../analytics/handoffs/sentry-replay.md).

The successful run used a temporary nano override in `development`. The source default remains `gpt-4.1-mini`. Eric and Chloe have approved keeping grounded local fallback and the current one-second provider budget; provider selection need not succeed on every tip. Eric requested `gpt-6-luna` as the target for GPT-4 text-coaching replacements; [owner migration work](../../../analytics/handoffs/coach-model.md) remains pending. The runtime item now tracks demo-host wording/voice timing and outcome verification, independently of accepted B5 evidence. Overall B5 still needs Sahil's brain evidence.

## Configuration and reproduction

Use the **replay project's** Client Keys (DSN) value, not the analytics DSN or a browser URL. Keep it in the ignored environment configuration used by replay:

```
SENTRY_DSN=<the kumite-replay DSN>
SENTRY_ENVIRONMENT=development
```

The merged implementation initializes Sentry once after environment loading. Its release defaults to `kumite-replay@<full commit>`; `SENTRY_RELEASE` can override it. The HTTP transaction contains the agent child and SDK-owned provider span. Prompts/outputs and HTTP bodies are excluded, and session correlation is hashed. Use the merged PR's `replay/SENTRY_VERIFICATION.md` for owner run commands and instrumentation details; the earlier initialization snippet is superseded.

Before the demo, verify the chosen model/client setup while keeping the approved deadline/fallback. Set `SENTRY_ENVIRONMENT=demo` on the demo host and retain fresh outcome counts/timings and release-tagged traces. Chloe checks spoken-tip wording and timing, including local fallback.

`/team-status` source matches report `on_branch` or `on_main` for initialization, the agent operation and environment handling. Those signals do not establish retention, provider selection, demo environment or latency reliability. The independently confirmed URLs in the verification record establish the accepted replay B5 evidence.
