# Chloe: analytics integration follow-ups

Owner: Track B. No app source changes were made by Track D. Follow the app's intent/spec review workflow for fixes.

## Integration update — PRs #19/#20

Chloe's C1 checker and C2 existing-screen fixes are merged into Eric's branch and integrated locally at `c87dcbe` without touching Eric's in-progress files. App typecheck/build and the combined 140-case analytics suite pass (139 passed, one opt-in cloud skip). Chloe's [static real-fixture acceptance](../../app/docs/acceptance/2026-10-18-stats-learning.md) confirms the corrected 1/4 throw fraction and first-fixed/current-regression wording. Growing-session flush/reconnect and native audio checks remain pending. The historical inspection below records the earlier `dc1f90c` baseline, not the current throw implementation.

Before using C1 for host advancement acceptance, address the [reset/late-learning false positive and reproduction](../evidence/pr20-integration.md). Chloe retains ownership of the checker and its test file. The new shared insights interface and optional C3 remain gated; no new route or consumer was introduced by these merges.

## Focus examples and shared data remediation

Eric's [eleven generated fixtures](../fixtures/insights/README.md), [display/state guide](insights-ui.md), and [proposal/TypeScript sketch](../INSIGHTS_PROPOSAL.md) are now included in the publication package. They cover the original C3 review prerequisite without relying on ignored local exports. Eric reviewed the states against the builder; Chloe's review and her app intent workflow are still required. Draft advice is labelled and can be replaced in a candidate UI by neutral “Review these moments” text while Garrett reviews mechanics.

For live Stats/Learning, analytics runs on Sahil's laptop against the exact absolute DATA_DIR used by the brain. [The native runbook](../INTEGRATION.md) now supplies a validating launcher, a recording-hash/API parity check and app URL setup. Local actual-HTTP verification passes with delayed learning and wrong content; Sahil's host path/address/access and actual growing-session/UI observations remain pending. See [the remediation verification](../evidence/insights-host-verification.md).

## First-release planning scope — October 18, 2026

**Option 1 is accepted by Eric and Sahil: improve the existing Stats and Learning screens.** Sahil will confirm the concrete subset with Chloe. The current app already has both screens and their analytics hooks. Prioritize trustworthy counts/denominators, current versus historical habit status, clear unavailable/pending values, and round/session freshness. When capacity allows, integrate the roadmap's focused recommendation and supporting moments into these existing surfaces.

This selects the existing-screen direction; Chloe's committed subset, capacity and dates remain pending her confirmation. Her agreement to keep local coaching fallback and the one-second provider budget does not imply agreement to extra UI work. A dedicated training/review screen is outside the first-release planning scope. Analytics definitions, exports and examples can proceed while app changes follow Chloe's workflow; new shared fields/routes still require team contract agreement. The [concurrent work plan](../TRACK_D_PARALLEL_PLAN.md) gives Eric the heavier lane and bounds Chloe's first app pass as C2; C3 is optional and interface-dependent.

Sahil reports M4 tips already reach the app through `/ws/coach`; final demo acceptance still includes Chloe checking spoken wording and timing for both provider and local-fallback paths.

## Source inspection at `dc1f90c`

| Area | Observed implementation | Concrete owner follow-up |
| --- | --- | --- |
| Throw fraction | `setData.ts:throwCounts` still adds breaks to events that already count attempts | Correct the denominator below |
| Fine-tune display | `LearningMetrics` declares `finetune`; `screens/Learning.tsx` does not render it | Implement the measured-or-pending panel; type presence alone is insufficient |
| Habit history | Latest `habit.fixed` drives the current belt; `time_to_mastery` appears under “To master” | Clarify that the round is historical first-fixed; retain current regressed status |
| Option bars | Bandit estimates are shown as percentages under “When the bot went for your habit” | Label estimated effectiveness; do not imply observed hit fractions |
| Round/reconnect refresh | `frame.tsx` already invalidates selected-session queries on summaries; hooks invalidate service queries on reconnect | Verify companion-file flush races and session switching; preserve existing working refresh paths |

This is source review, not an app build or native visual verification. Track D has changed no `app/` source. Chloe confirms which follow-ups fit her bounded first pass through the app's intent/spec workflow.

## Throw denominator

`app/src/renderer/src/main-window/setData.ts:throwCounts` currently returns `total = landed + broken`. The tracker emits `throw` for every attempt, then additionally emits `throw_break` when it is escaped. Count `total` as bot throw attempts targeting the human; `broken` counts the human's successful break events. Do not add breaks to attempts again.

Acceptance: two bot `throw` events and one human `throw_break` show **1/2 (50%)**, matching `/stats`. Repeat with `human_slot=1` and a side switch; block slots remain authoritative. No attempts must display unavailable data rather than a fabricated zero rate.

## Learning and fine-tune panel

Point `KUMITE_ANALYTICS_URL` at real analytics on :8767 and run the mock with `--services brain,replay`. The service retains accuracy rounds, drift markers, first detection/mastery and unknown learning extension fields. It does not claim to infer deliberate re-tests.

Read `finetune.before` and `finetune.after` from `/learning`. Both remain null until Sahil writes a valid eval file. Display measured before/after values only when both are numbers; hide the comparison or show pending otherwise. The same eval file and validation now drive the mock.

Use `data/samples/live_learning` for the real four-round acceptance set and read its README first: low defense is detected but never fixed; after-block is first fixed in round 2 and regresses in round 3; fine-tune comparison is unavailable. Use `data/samples/synthetic` for the separate three-round walkthrough, labelled synthetic. Previous app typecheck/build results are historical; rerun them for Chloe's implementation and retain native visual/play-session observations.
