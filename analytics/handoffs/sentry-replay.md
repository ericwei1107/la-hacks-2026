# Garrett: retained coach-agent monitoring

Owner: Track C. Project: `kumite-replay`; org: `university-of-maryland-ma`. Track D has not edited `replay/`.

## B5 evidence accepted — October 18, 2026

[PR #15](https://github.com/ericwei1107/la-hacks-2026/pull/15), branch `codex/replay-sentry`, is merged as `c7e11f209460b7498dec39ea209e3740385fecc1`. Sentry MCP independently confirmed the retained [HTTP → agent → provider trace](https://university-of-maryland-ma.sentry.io/explore/traces/trace/bc9fad3bd3974dbb9145165d02f9605c/), `coach.outcome=provider_selected`, actual model `gpt-4.1-nano-2025-04-14`, 387 input / 24 output tokens, release `kumite-replay@33d058ff7fbfe7b86a02f84e8ca24b3c2c8ff9c9`, and environment `development`. The full evidence and confirmed fallback links are in [Sentry verification](../SENTRY_VERIFICATION.md#b5-retained-replay-coach-evidence--october-18-2026).

The request used the public contract round-summary example and the real OpenAI API on verification port 8776. [PR #16](https://github.com/ericwei1107/la-hacks-2026/pull/16) is also merged (`4787b3268d8bc086653b66b62d6039c8c899a7f0`) and retains the authoritative [owner evidence and latency record](https://github.com/ericwei1107/la-hacks-2026/blob/4787b3268d8bc086653b66b62d6039c8c899a7f0/replay/SENTRY_VERIFICATION.md#retained-live-evidence-2026-10-18). Replay's B5 evidence requirement is satisfied. Overall B5 still needs Sahil's five-operation decision trace, waterfall screenshot and tracing on/off timings. These independent service traces do not prove distributed propagation or execution on the demo host.

## Implemented behavior

The reviewed PR initializes Sentry once after environment loading and before FastAPI construction. A `gen_ai.invoke_agent` child retains the HTTP parent; the SDK instruments the actual `Responses.create` call as `gen_ai.responses`. It replaces the previous uninstrumented `Responses.parse` call while keeping strict schema selection and local validation. No duplicate exporter or synthetic provider spans are required.

The current round provider budget is **1.0 second**, with a 0.9-second OpenAI client timeout, no retries and local fallback. This supersedes the old handoff's five-second assumption. Distinguish `provider_selected`, `fallback`, `deterministic` and `local`; an HTTP 200 alone does not prove provider selection. Current round coaching is tool-free.

Telemetry excludes AI inputs/outputs, request contents and raw player/session identity; session correlation is hashed. Keep those controls when reproducing evidence. Model name, token usage, outcome, release and environment are sufficient for this evidence. Garrett reports coarse IP-derived geography may still be added by Sentry; no project setting change was made.

## Demo decision — approved by Eric and Chloe, October 18, 2026

Eric chose to keep grounded local fallback available and preserve the existing one-second provider budget; Chloe agrees. Consistent provider selection is not required for every spoken tip. Demo acceptance still requires Chloe to check tip wording and voice timing on the demo host, including fallback runs. Provider latency measurements are useful for improvements but do not block this agreed fallback behavior.

Eric also requested moving GPT-4 text coaching calls to **GPT-6 Luna**, API model ID `gpt-6-luna`. Sahil's coordination message and Garrett's implementation scope are in [the model handoff](coach-model.md). This is the requested target; the current replay source/default is still mini until the owner implements and verifies the switch. Keep the accepted GPT-4 trace as historical B5 evidence.

### Remaining owner work

Garrett used `OPENAI_COACH_MODEL=gpt-4.1-nano` only for the successful evidence process. The recorded service default remains `gpt-4.1-mini`. His merged record reports nano HTTP timings of 1046, 855 and 1034 ms, with one provider-selected tip; mini exceeded the budget at approximately 1.05–1.43 seconds. The earlier retained fallback traces independently confirm fallback outcomes: the owner attributes one to missing account credit/timeout and the other to the default model exceeding the deadline after credit was added. These are separate from the three nano timing attempts and do not establish reliable provider use for either model.

1. **Garrett and Sahil:** coordinate the requested `gpt-6-luna` text-coaching migration and validate request/schema compatibility and returned tips. Local fallback remains acceptable; do not extend the deadline to force a provider success.
2. **Garrett, for any latency work:** investigate client setup/connection reuse and compare candidate settings under the existing deadline. Report comparable attempt counts, provider-selected/fallback counts and latency; changing the default or deadline is a separate owner change.
3. **Integration host owners:** run the chosen setup on the demo host with `SENTRY_ENVIRONMENT=demo`, retain the deployed release and real outcome traces, and verify the spoken tip arrives within the agreed timing. The retained development trace does not close this check.

No additional DSN, analytics release or replay B5 evidence is needed from Eric for the accepted trace. This update records the evidence; it does not merge owner code into this checkout or change the model/default/deadline.
