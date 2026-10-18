# Six concurrent workstreams: 2–4 hour analytics demo

October 18, 2026. Eric confirmed 2–4 hours remain. Assign five streams to Eric and one to Chloe. This is an execution draft, not a claim that these tasks have been implemented or a launch of implementation agents. Two read-only planning reviews informed the split.

**Ship this.** Existing Stats and Learning screens, accurate fractions, one automatic low-defense focus, a small list of up to three relevant moments, and completed-round/pending freshness. Use neutral “Review these moments” text until mechanical advice is reviewed. Keep the existing first-fixed/current-status correction. Demonstrate real detection/exploitation; human improvement is not established by the existing sample.

**Do not restart completed work.** Current files already include metric evidence, focus selection, deterministic exports, eleven internal examples, host tooling and app correctness changes. The current `analytics/main.py` conditionally registers insights, and `analytics/insights.py` contains `public()` and `register()`. Status documents saying the projection/experimental real route is absent are stale. Presence of code is not evidence of all-owner interface approval, current tests, deployment or UI acceptance.

**Cut now.** New historical comparisons, practice/retention pilots, heatmaps, timing distributions, punish recognition funnels, manual-focus controls, predictor/trial instrumentation, aligned new charts, replay takeover, report enrichment, new cloud infrastructure/backfills, a full scenario-player framework and broad redesign. Do not enable punishment as an automatic focus. Keep sponsor trace collection as opportunistic evidence work, not a blocker for player-facing readiness.

**One short shared setup, then parallel work.** Spend at most the first ten minutes establishing the common source snapshot, existing interface, exact file owners and demo dataset. All six streams can inspect their files and prepare checks during setup. Freeze a small existing public view, using `public(InsightRepository(...).snapshot(sid, limit=3))`, rather than inventing another schema. Lane 2 owns the schema/example decisions; lane 1 alone changes the implementation in `insights.py`. Existing full internal fixtures must not be mistaken for public HTTP responses. Retain required quality, synthetic and freshness fields even when the UI does not show every field.

**Six assignments.**

| Lane | Owner | Bounded outcome | Exclusive write scope |
|---|---|---|---|
| 1. Backend stabilization | Eric session 1 | Existing counts, evidence, focus/export and experimental real route agree with the frozen public view | `analytics/stats.py`, `evidence.py`, `focus.py`, `insights.py`, `main.py`, `tests/test_insights.py`; new `tests/test_demo_metrics.py` only if needed |
| 2. Interface and UI fixtures | Eric session 2 | Minimal v1 schema, generated public examples, TypeScript sketch and precise display rules | `analytics/insights_v1.schema.json`, `INSIGHTS_PROPOSAL.md`, `handoffs/insights-ui.md`; new `demo_examples.py`, `fixtures/demo-insights/`, `tests/test_demo_examples.py` |
| 3. Independent acceptance and final integration | Eric session 3, coordinator | Find cross-module defects, run final verification and integrate delivered changes once | New `analytics/tests/test_demo_acceptance.py`, `analytics/evidence/demo-acceptance.md`; status/README corrections after code freeze |
| 4. Checker and host rehearsal | Eric session 4 | Correct advancement proof; portable source-matched launch and actual host rehearsal when access exists | `analytics/integration_check.py`, `demo_host.py`, `benchmark_insights.py`, `INTEGRATION.md`; checker/host tests and a dedicated host-results receipt |
| 5. Demo package and evidence | Eric session 5 | Reproducible exports, short presentation script, claim ledger and fallback walkthrough | `analytics/submission/`, new `analytics/evidence/demo-package.md`; generated output only in ignored `data/analytics/demo/` |
| 6. Existing-screen UI | Chloe session | Small focus card, fractions, three moment rows, honest freshness and correct labels | `app/**`, following `app/AGENTS.md` |

These are five Eric sessions plus Chloe's session. Lane 3 also coordinates; do not create a seventh integration owner. Everyone can read other lanes' files. Fixes outside a lane's scope go to that file's owner. Nobody edits `game/`, `replay/`, source fixtures or frozen `contracts/` as part of the default sprint.

**Lane 1: stabilize, do not redesign.**

Use the real M3 sample: low blocks 0/16, throws 1/4, estimated punishes 0/6, low-defense focus, after-block first fixed in round 2 and later regressed, no low-defense mastery, null fine-tune comparison. Verify current values rather than relying on old test-count claims. Preserve calculation version 4 and existing endpoints; report any unavoidable semantic correction before changing persisted calculations.

Keep completed-round population, source identity, pending learning, invalid data suppression and bounded moments consistent. Use the existing experimental route for validation; leave default-on shared consumption gated on actual owner agreement. Match lane 2's frozen public examples. Neutralize unreviewed advice in the consumer rather than invent new mechanics. No new public features after the first working route/fixture checkpoint.

Done: focused insight tests pass; the public view validates; the real sample matches its evidence; missing learning/report data and source errors produce the documented states. Handoff: exact changed files, tested snapshot, working command, remaining defects. Lane 1 is the sole editor of both API registration and public projection because they currently share implementation files.

**Lane 2: unblock Chloe immediately.**

First deliver one public real-sample JSON and a type sketch, then add pending-learning, no-opportunities, invalid and synthetic examples. Use a separate demo-example generator; do not rewrite the eleven existing internal examples or edit their generator during this sprint. Generate public examples through existing production functions. Five useful examples are sufficient; do not expand the state matrix unnecessarily.

Explain metric fractions, nulls, estimates, draft advice, embedded event detail, snapshot changes and view/session identity. Keep only the UI fields Chloe needs, while preserving existing semantics. Clearly document the existing flag and approval status rather than claiming the route is absent. Freeze names once Chloe starts; subsequent changes must be coordinated and essential.

Done: Chloe can render the real card and moment list without the backend running; generated public examples validate and regenerate deterministically. Do not edit `contracts/`. If four-owner agreement is obtained, draft the exact shared-contract patch for the coordinator to route through the established process; avoid a second competing schema author.

**Lane 3: independent acceptance and integration owner.**

Begin immediately by auditing source counts independently and preparing a small acceptance matrix. Use in-process HTTP clients and temporary copies of data to check real route/export/public-example parity, late learning, invalid source and unknown session behavior. No new mock route is required: existing mock brain/replay plus real analytics are enough. Only add mock-specific code if an actual blocker is demonstrated, then assign its file owner explicitly.

Report core defects to lane 1 and example defects to lane 2. Do not patch their files yourself while they are working. After the first backend/UI checkpoint, prioritize stopping defects over optional work. After freeze, run analytics/mock suites, fixture drift check, frozen contract validator and the relevant existing smoke checks against one recorded source snapshot. Chloe runs app build/typecheck and visual acceptance. Host-specific checks remain lane 4's responsibility.

Own branch/index/integration operations for the sprint. No worker runs `git add .`, broad cleanup, stashing, resets, independent merges or publication. Existing dirty implementation must be preserved in the common baseline; a clean-HEAD worktree would omit it. Use the current shared tree with strict file ownership, or separate worktrees only after a reviewed baseline carries the relevant existing work. Publish only specifically reviewed paths through the team's existing workflow. No automatic deployment is part of this planning draft.

Done: one pass/fail list tied to actual tested code, clear remaining limitations and a reproducible demonstration. Correct stale status prose only after the implementation state is stable.

**Lane 4: prove current source and current advancement.**

Inspect the documented checker reset issue first. A sequence where stats moves 4→5→4 and learning moves 4→4→5 must not falsely pass: there is no current common completed round 5. Acceptance should require the correct session and a common currently completed round beyond the appropriate initial baseline, with resets handled explicitly. Add meaningful checker cases for reset, delayed learning, wrong identity and static input.

Reuse the existing launcher/source parity tools. Validate the same absolute DATA_DIR on brain and analytics; health alone is insufficient. This lane exclusively owns real socket-based rehearsal during parallel development. Use temporary non-conflicting local ports for local checks; do not stop existing user services or compete for the demo host's ports.

With actual access, check launch, a growing session, delayed learning, reconnect, session switch, shutdown and displayed freshness with Chloe. Record what was actually observed. A static sample is useful playback but must not satisfy a required-live-advance check. If the host is unavailable, finish local temporary-data rehearsal and retain exact Windows commands; label native observations pending. Do not build networking or a new remote file-sync system.

Done: checker false-positive fixed and tested; local source/flush rehearsal passes; actual Windows results recorded if possible. Local measurements do not become native-host evidence.

**Lane 5: make the demo usable even if new UI misses the cut.**

Generate existing JSON/Markdown exports to an ignored output directory. Prepare a 60–90 second script: identify the real session, show 0/16 lows and bot prediction history, inspect a relevant recorded moment, explain the recommended next focus. Include source/session/version identity and reproducible commands in the claim ledger. Verify the final exports again after the common freeze; earlier exports are rehearsal material.

Prepare two versions: existing screens plus the small insights UI if integrated, or existing corrected screens plus clearly identified post-set export if not. No new slide deck, dashboard site, report model or video tooling. Keep report enrichment optional; unavailable best moves do not block event review. Add existing sponsor evidence only when retained and verified; do not wait on Sahil's trace to finish the demo package. Do not send messages or publish submissions.

Done: the presenter can follow one short script with exact files/commands, and every claim has an actual source. No invented player improvement, fine-tune gain or deliberate retest.

**Lane 6: Chloe's deliberately small UI scope.**

Start immediately with already-supported wording: “estimated effectiveness,” unavailable values, synthetic labels and existing correctness review. Follow the app's required intent/spec/code/review sequence. One owner handles services/types/hooks and both screens to avoid app-internal merge conflicts.

Against lane 2's public fixture, add one focus card on Stats, three small moment rows showing round/frame and embedded event detail, and “through completed round N”/pending text. No new screen, chart, manual selector, evidence-fetch route, report dependency or deep replay inspector. Existing Learning charts remain. Use “Review these moments” while action text is unreviewed. Show 1/4 throw breaks as an early signal under the existing policy, not an automatic focus.

Refetch through existing round/reconnect/session triggers. Clear stale selection on changed source/session; a response from an old session must never populate the new one. Preserve valid recording counts while learning is pending. Switch the data source to the real experimental route only within the actual owner-agreed integration scope; fixture-backed UI remains a development preview. Default-on shared consumption still needs the repository's interface agreement.

Done: typecheck/build pass; the five fixture states are readable; keyboard selection works; the real-data integration and host observations are recorded separately. No new app automated tests, per the owner workflow. If time runs out, retain the existing corrected screens and use lane 5's post-set export.

**Synchronization points: the only planned waits.**

1. First ten minutes: lane 2 freezes the existing public shape with lane 1 and supplies the first real example to Chloe. Other lanes prepare checks, commands and narration immediately.
2. First checkpoint, target around 30–45 minutes: Chloe renders one fixture; lane 1 serves the same shape locally; lane 3 compares them. This is a scheduling target, not a measured completion promise.
3. Integration checkpoint: swap fixture development input for approved real transport; verify an actual update. Lane 4 owns data/ports and pairs with Chloe on observation.
4. Final freeze: stop features and complete release checks/rehearsal. Lane 3 collects results; lane 5 regenerates the final package.

**Timebox.**

| Time remaining | Work policy |
|---|---|
| 2 hours | Ten-minute setup; first visible checkpoint by roughly minute 35; freeze features by minute 60; reserve the final hour for integration, defect fixes and rehearsal |
| 3–4 hours | Same early checkpoint; freeze new features by halfway; use extra time for actual host observation and defects, not deferred analytics |
| At the midpoint with no stable transport/approval | Demo the existing screens plus deterministic post-set export; keep preview UI work from consuming rehearsal time |
| Last 30 minutes | No new dependencies, refactors, API fields or cloud changes; fix only demo-stopping defects and rehearse |

**Remaining inputs and concerns.** The remaining logistics are the actual deadline, Sahil's absolute DATA_DIR/reachable host and access window, and whether the shared insights interface has already received the required owner agreement. These are external gates; code inspection does not settle them. Continue local/fixture/export work while they are unresolved. Do not add producer counters or require Garrett's report as a deadline dependency.

There is substantial uncommitted work in the common tree, and status documents are contradictory. Rebuilding or overwriting it is the largest avoidable risk. Fixture generators can drift if semantics change mid-sprint, so coordinate one regeneration after freeze. Six streams do not make Chloe's single integration path or the Windows host six times faster; restrict their scope and meet early.

**Execution capacity.** Six genuinely simultaneous processes means five Eric sessions plus Chloe's session, each using this file's assignment. This conversation's agent tool has four active slots total, so it can run fewer lanes at once with queued work; it cannot host six agents simultaneously. The draft does not imply six implementation processes are already running.

**Paste into each worker session, followed by its lane text above.**

> Work only on your assigned lane in analytics/SIX_LANE_DEMO_PLAN.md. Inspect existing implementation before writing; do not recreate completed work. Treat the listed files as your exclusive write scope and report cross-scope defects to the coordinator. Preserve the frozen interface and existing APIs. Use temporary data for destructive test scenarios. Do not edit contracts, source fixtures, another track, Git history or credentials. Do not commit, merge, publish or start services on shared ports independently. Deliver the smallest working demo increment, exact changed paths, checks actually run and any remaining blocker. Cut optional work at the coordinator's freeze.

**Existing immediate checks (planning did not rerun them).**

```sh
.venv/bin/python -m analytics.insight_examples --check
SENTRY_DSN= DATABASE_URL= .venv/bin/python -m unittest discover -s analytics/tests -p test_insights.py -v
.venv/bin/python contracts/validate.py
```

Expect the eleven existing internal examples to match, focused insight tests to pass and frozen contracts to validate. New public-demo fixtures, route acceptance and checker-reset tests are lane deliverables, not results claimed by this draft.
