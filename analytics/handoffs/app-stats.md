# Chloe: analytics integration follow-ups

Owner: Track B. No app source changes were made by Track D. Follow the app's intent/spec review workflow for fixes.

## First-release planning scope — October 18, 2026

For Sahil's UI-scope question, plan around **option 1: improve the existing Stats and Learning screens**. The current app already has both screens and their analytics hooks. Prioritize trustworthy counts/denominators, current versus historical habit status, clear unavailable/pending values, and round/session freshness. When capacity allows, integrate the roadmap's focused recommendation and supporting moments into these existing surfaces.

This is a scope recommendation, not a claim that Chloe has committed capacity or dates for the additions. Confirm the concrete subset with Chloe before promising UI delivery. Her agreement to keep local coaching fallback and the one-second provider budget does not imply agreement to extra UI work. A dedicated training/review screen is outside the first-release planning scope. Analytics definitions, exports and examples can proceed while app changes follow Chloe's workflow; new shared fields/routes still require team contract agreement.

Sahil reports M4 tips already reach the app through `/ws/coach`; final demo acceptance still includes Chloe checking spoken wording and timing for both provider and local-fallback paths.

## Throw denominator

`app/src/renderer/src/main-window/setData.ts:throwCounts` currently returns `total = landed + broken`. The tracker emits `throw` for every attempt, then additionally emits `throw_break` when it is escaped. Count `total` as bot throw attempts targeting the human; `broken` counts the human's successful break events. Do not add breaks to attempts again.

Acceptance: two bot `throw` events and one human `throw_break` show **1/2 (50%)**, matching `/stats`. Repeat with `human_slot=1` and a side switch; block slots remain authoritative. No attempts must display unavailable data rather than a fabricated zero rate.

## Learning and fine-tune panel

Point `KUMITE_ANALYTICS_URL` at real analytics on :8767 and run the mock with `--services brain,replay`. The service retains accuracy rounds, drift markers, first detection/mastery and unknown learning extension fields. It does not claim to infer deliberate re-tests.

Read `finetune.before` and `finetune.after` from `/learning`. Both remain null until Sahil writes a valid eval file. Display measured before/after values only when both are numbers; hide the comparison or show pending otherwise. The same eval file and validation now drive the mock.

Use `data/samples/synthetic` as `DATA_DIR` for the checked-in three-round walkthrough. It is synthetic evidence and must be identified as such. The app typecheck and build pass; final native visual/play-session verification belongs to the owners' integration pass.
