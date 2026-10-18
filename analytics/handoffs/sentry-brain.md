# Sahil: retained decision traces

Owner: Track A. Project: `kumite-brain`; org: `university-of-maryland-ma`. Track D has not edited `game/`.

## M4 status — October 18, 2026

M4's brain API and coach forwarding are on main: `97c3b5f` adds the API and `e97ac4a` connects the bot and coach outlet; both are ancestors of inspected `origin/main` at `c7e11f2`. Source inspection confirms brain :8765, round-summary POSTs to Garrett's `/coach/round`, and tips published through `/ws/coach`. Sahil reports live verification with Chloe's app; Track D has not independently repeated that Windows/game integration check.

Sahil reports the previously forwarded DSN omitted its public key. On October 18, Track D retrieved the existing Default client key again through Sentry MCP `find_dsns` and verified that the full value includes a nonempty public key, host `o4512273697341440.ingest.us.sentry.io` and project ID `4512273716281344`. The corrected full value is supplied in the conversation for private forwarding, not stored in this handoff. Retrieval and format checks do not prove it has been set in Sahil's running process or that ingestion works. Org membership/invite delivery remains unverified; a DSN does not grant viewing access.

**Private delivery complete, reported by Eric:** Eric confirms he has already sent the full DSN to Sahil privately. The delivery blocker is cleared; no duplicate DM is needed. Process configuration, owner instrumentation and live evidence remain unverified. Sahil expects to return evidence about 30 minutes after receiving/configuring it; this is an owner estimate, not a completed run or a confirmed start time.

Source inspection at `dc1f90c` found no Sentry initialization or decision spans in `game/`; owner implementation remains pending. The inspected `game.bot` entry point also does not load `.env`. Export `SENTRY_DSN` in the actual launch environment, or explicitly load that file in the owner's launcher. The [setup request](../../tools/status/requests/sentry-brain.md) includes a credential-free local preflight.

The M4 prerequisite has landed. Instrument at the agreed 5% root sampling rate and retain the real decision trace URL, waterfall screenshot and tracing on/off comparison. Brain instrumentation and retained evidence remain pending. The real learning bundle has already been received and its local/cloud intake is recorded in [B4 verification](../LIVE_LEARNING_VERIFICATION.md).

Sahil accepts **option 1: improve the existing Stats and Learning screens**, matching Eric's selected scope, and will confirm the concrete subset with Chloe. Her capacity, implementation commitment and dates remain unconfirmed. The bounded tasks are in [Chloe's handoff](app-stats.md) and [the concurrent work plan](../TRACK_D_PARALLEL_PLAN.md). Eric and Chloe's fallback/timing decision and Eric's requested `gpt-6-luna` text-coaching target are in [the model handoff](coach-model.md).

Instrumentation locations previously inspected: `game/hotloop.py:run_session`, its `frames` generator, and `game/bot.py:BotHooks.frame`. M4 has changed the entry/API wiring; check the current owner source before placing contexts and preserve learning calls from the frame hook.

Initialize the Sentry Python SDK once in the game entry process, before work starts; use the existing project DSN through environment variables. For Sahil's promised brain run, set `SENTRY_ENVIRONMENT=demo-laptop` and set the Sentry release to the full deployed `main` Git SHA. This supersedes the earlier `demo` label for this brain run; other services retain their separately configured environment labels. Keep reads and input release behavior unchanged when telemetry is disabled.

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

Sahil's minimum promised timing comparison is decision-loop **p50/p95 in milliseconds**, **one practice round with tracing off and one with tracing on at 5% sampling**, with the same settings. Record the full deployed commit, machine, mode, session/round, duration, sample count and the exact boundaries of the same decision-loop measurement in both runs. Median is p50. Maximum and missed-frame/overrun counts are useful additional evidence if available, not invented requirements already fulfilled. Keep the separate transport-unavailable check explicit. Sahil owns the acceptable timing decision; report the measurements without inventing a threshold or treating two rounds as a general benchmark.

Source presence alone does not close this handoff. No fake read or input spans should be added to the analytics service to simulate completion.

Use the [brain evidence template](../evidence/brain-decision-template.md) for the return handoff. Sahil has committed to sending the 5% decision trace URL, waterfall screenshot and on/off timings after setting the corrected DSN; those artifacts have not yet been received or verified.

**Sahil update, about 03:40 PT on October 18:** instrumentation is going in now. Within the hour he will send the trace URL, the waterfall screenshot, the full SHA used as release, environment `demo-laptop`, and tracing off/on p50/p95 with sample counts. Nothing has been received or verified yet; B5 stays open until those artifacts are checked against the template.
