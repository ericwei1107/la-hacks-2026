# Sahil: GPT-6 Luna coaching handoff

Requested by Eric on October 18, 2026. Eric and Chloe approved keeping grounded local fallback and the current one-second round-provider budget. Consistent provider selection is not required for every spoken coaching tip.

Eric requests switching GPT-4 text-coaching calls to **GPT-6 Luna**, API model ID `gpt-6-luna`. The [official OpenAI model page](https://developers.openai.com/api/docs/models/gpt-6-luna) confirms the model identifier and Responses API support. Availability for the team's API project and deadline performance still need owner verification.

## Message for Sahil

Sahil — Chloe and I agree to keep local coaching fallback and the existing one-second provider budget so spoken tips stay timely. Please coordinate with Garrett to switch GPT-4 text-coaching calls to GPT-6 Luna (`gpt-6-luna`). Preserve the deadline and fallback while making the change. Verify request/schema compatibility, tip quality and timing on the demo host; record the actual model, provider-selected/fallback counts and Sentry release/environment. We don't need an OpenAI-selected tip on every round. Garrett's existing replay B5 trace is accepted; your decision trace, waterfall and tracing on/off timings are still needed to finish B5.

## Owner scope and acceptance

- **Sahil:** coordinate the demo host's model configuration with Garrett and Chloe. The request concerns OpenAI text coaching; no change to local Laya tactical inference or the frame loop is implied.
- **Garrett:** replay owns the current GPT-4 text defaults. `OPENAI_COACH_MODEL` selects round coaching and `OPENAI_CHAT_MODEL` can override post-set chat. Update applicable defaults/configuration to the requested target within the owner branch; verify the actual request options and structured output work with Luna. Account access and a new provider success have not been tested in this update.
- **Chloe:** rehearse tip wording and spoken timing for both provider-selected and local fallback responses on the demo host.
- **Evidence:** retain fresh model/outcome/timing and release/environment observations. Preserve the already accepted GPT-4 replay trace as historical B5 evidence; do not relabel it as Luna.

This handoff records the request. Replay/game source and live environment settings have not been changed by Track D. External notification delivery is tracked separately; a local file is not a sent message.
