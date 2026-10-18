# Sahil: retained decision traces

Owner: Track A. Project: `kumite-brain`; org: `university-of-maryland-ma`. Track D has not edited `game/`.

## M4 status — October 18, 2026

M4's brain API and coach forwarding are on main: `97c3b5f` adds the API and `e97ac4a` connects the bot and coach outlet; both are ancestors of inspected `origin/main` at `c7e11f2`. Source inspection confirms brain :8765, round-summary POSTs to Garrett's `/coach/round`, and tips published through `/ws/coach`. Sahil reports live verification with Chloe's app; Track D has not independently repeated that Windows/game integration check.

Sahil confirms brain Sentry is next once he receives its DSN. Sentry MCP returned the existing `kumite-brain` project DSN on October 18; project ID `4512273716281344`. The credential is supplied to Eric for private forwarding, not stored in this handoff. Org membership/invite delivery remains unverified. Providing a DSN enables ingestion; it does not establish the recipient's Sentry viewing access.

The M4 prerequisite has landed. Instrument at the agreed 5% root sampling rate and retain the real decision trace URL, waterfall screenshot and tracing on/off comparison. Brain instrumentation and retained evidence remain pending. The real learning bundle has already been received and its local/cloud intake is recorded in [B4 verification](../LIVE_LEARNING_VERIFICATION.md).

For the first-release UI question, use **option 1: improve the existing Stats and Learning screens** as the planning scope. Proposed improvements and owner-capacity limits are in [Chloe's handoff](app-stats.md). Eric and Chloe's fallback/timing decision and Eric's requested `gpt-6-luna` text-coaching target are in [the model handoff](coach-model.md).

Instrumentation locations previously inspected: `game/hotloop.py:run_session`, its `frames` generator, and `game/bot.py:BotHooks.frame`. M4 has changed the entry/API wiring; check the current owner source before placing contexts and preserve learning calls from the frame hook.

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

For the timing comparison, record the deployed commit, machine, mode, session/round, sample count and the same frame/poll duration measurement in both runs. Retain median, p95, maximum and missed-frame/overrun counts if available. Use comparable workload and duration, and include transport-unavailable behavior. Sahil owns the acceptable timing decision; report the measurements without inventing a threshold.

Source presence alone does not close this handoff. No fake read or input spans should be added to the analytics service to simulate completion.
