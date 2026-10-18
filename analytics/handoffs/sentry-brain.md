# Sahil: retained decision traces

Owner: Track A. Project: `kumite-brain`; org: `university-of-maryland-ma`. Track D has not edited `game/`.

Inspected baseline: local `game/hotloop.py:run_session`, its `frames` generator, and `game/bot.py:BotHooks.frame`. The refreshed `origin/sahil/game` also calls `Learning.step` and `Learning.round_end` from that hook. Preserve those owner changes.

Initialize the Sentry Python SDK once in the game entry process, before work starts; use the existing project DSN through environment variables. Set `SENTRY_ENVIRONMENT=demo` only on the integration/demo host. Set a release containing the deployed commit. Keep reads and input release behavior unchanged when telemetry is disabled.

Instrument where work actually occurs:

| Operation | Current location |
| --- | --- |
| `read` | Snapshot read inside `game.hotloop.frames`, before yielding |
| `decode` | `st.build_state` and `tracker.step` in `run_session` |
| `reflex` | `self.reflex.step` in `BotHooks.frame` |
| `tactical` | Detector/learning/tactical calls in `BotHooks.frame`; include real Laya inference when wired |
| `input` | Sequencer/pad execution in `BotHooks.frame` |

Use one sampled `decision` transaction for a complete selected frame iteration. Start its context before the selected snapshot read and finish it after the hook/input work, including exceptions and loop exits. The generator boundary must preserve the same context; a transaction started only after `frames` yields cannot include the read as its child. Do not add a transaction to every span or emit network requests synchronously in the loop. Start with a 5% root sample rate and measure hot-loop timing with tracing on/off.

The SDK pattern is `sentry_sdk.start_transaction(op="decision", name="game.decision")` with nested `sentry_sdk.start_span(op=..., name=...)` contexts. Read [the Python tracing API](https://getsentry.github.io/sentry-python/api.html) for context lifetime. Add frame/round only as trace data; game timing still uses the round frame counter.

## Acceptance

1. Read-only/offline game behavior, kill switch and pad release still work with the DSN absent and network unavailable.
2. One retained real decision trace contains the five actual pipeline operations, tagged with the deployed release/environment.
3. Record the direct trace URL and capture its waterfall screenshot under `analytics/evidence/` with no credentials visible.
4. Compare frame/poll timing with tracing disabled and enabled. Confirm SDK transport work does not block the hot loop.

Source presence alone does not close this handoff. No fake read or input spans should be added to the analytics service to simulate completion.
