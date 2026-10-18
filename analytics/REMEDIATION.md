# Track D remediation — October 17, 2026

## Implemented

Calculation version **3** uses the same stats reducer for file endpoints, mock analytics, calculated database rounds and trend snapshots. States retain situation context; non-null winners are applied in recording order after metadata; a human hit can satisfy only the most recent unmatched qualifying punish opportunity in its round. The provisional punish allowance remains ten frames.

Live stats validate known records, count invalid records in `skipped_lines`, and ignore unsupported types. Strict learning/trend readers return 503 for invalid complete data and wait for partial trailing JSON tokens. Recording identity and prefix hashes detect larger replacements and in-place corrections. Invalid metadata is isolated to its session.

API database connections use two-second connection/statement limits. Database work does not hold the file lock; concurrent requests can use files while a database request is pending. Importer limits remain five seconds for connection and fifteen seconds for statements. Calculation version participates in both import and aggregate fingerprints.

The mock shares learning normalization, evaluation validation and trend calculations with real analytics. Companion learning files take precedence; inline learning remains a mock-fixture fallback. Invalid existing eval files return 503, missing ones return nulls. The launcher restores signal handlers after shutdown, with a Windows fallback for unsupported asyncio signal handlers. Native Windows execution remains unverified.

## Verification

Final suites: analytics 73 cases (72 pass, one opt-in cloud skip); mocks 39 pass. The cloud case passed separately without skipping: **112 unique tests passed across offline/live runs**, including sixteen new regression cases. Frozen examples and the bundled synthetic recording validate.

Baseline: `e876d8b` plus this working-tree change. No verification claim implies this work was committed or deployed on Sahil's laptop.

- Live Tiger Data temporary-schema integration: passed. Proves four hypertables, continuous aggregate, aggregate reads with the file reducer disabled, stale-source fallback, corrections, rollback and reconnect.
- Production backfill at calculation version 3: `imported=4 unchanged=0 invalid_sessions=0`; immediate repeat: `imported=0 unchanged=4 invalid_sessions=0`.
- Actual-port analytics + mock brain/replay smoke: passed learning, trends, eval refresh and WebSocket playback; clean shutdown.
- Actual-port all-mock smoke: passed HTTP, CORS, recording download, both WebSockets, occupied-port handling and SIGINT cleanup.
- Existing Electron app: locked dependencies installed, typecheck and production build passed. No app source was edited. This does not claim a native Windows visual check.
- Retained analytics Sentry operation spans: see [Sentry evidence](SENTRY_VERIFICATION.md). Health instrumentation is locally verified; its existing inbound filter is intentional.

Run the complete offline suites and contracts from the repo root:

```sh
.venv/bin/python -m unittest discover -s analytics/tests -v
.venv/bin/python -m unittest discover -s tools/mock/tests -v
.venv/bin/python contracts/validate.py
.venv/bin/python contracts/validate.py data/samples/synthetic/recordings/2026-10-17T13-05-00_synth_djin_vs_kaz.jsonl
```

## Owner handoffs and completion gates

- [Sahil: decision tracing](handoffs/sentry-brain.md). Requires owner code and a retained `decision` waterfall covering the actual read/decode/reflex/tactical/input pipeline.
- [Garrett: coach monitoring](handoffs/sentry-replay.md). Replay B5 evidence verified October 18: PRs #15/#16 are merged and the owner record retains a real HTTP → agent → OpenAI provider trace with model/usage and release/environment. Eric and Chloe approved local fallback and the existing one-second budget. The requested [GPT-6 Luna text-coaching migration](handoffs/coach-model.md) and demo voice check remain owner work. See [retained evidence](SENTRY_VERIFICATION.md#b5-retained-replay-coach-evidence--october-18-2026).
- [Chloe: throw counts and learning display](handoffs/app-stats.md). The app currently adds successful breaks to a throw count that already includes them.
- Sentry org invitations remain manually unverified. No messages or account permission changes were made.

**Cross-track Sentry sponsor completion remains blocked on Sahil's decision trace, waterfall screenshot and tracing on/off timings.** Analytics and replay evidence is retained in [the evidence index](evidence/README.md); the game waterfall is still pending. Independent service traces do not establish distributed propagation across services. Demo-environment execution also remains unverified.

## Partial and deferred work

- Historical first mastery, later `fixed`/mastery changes and unknown extension fields are preserved. There is no derived re-test API: post-fix observations alone do not prove a deliberate probe. Owner-supplied regression/re-test evidence is required before claiming this feature.
- Laya eval, training data, Veri job, before/after evaluation and checkpoint selection belong to Sahil under current `CLAUDE.md`. Acceptance: session-held-out measured accuracies written atomically to `DATA_DIR/eval/<session_id>.json`; Chloe renders both values when present.
- Track D archive: reproducible JSONL-to-Parquet conversion plus a DuckDB query with matching session/round counts. Optional Spaces backup remains deferred.
- Devpost and challenge write-ups: explain actual measurements and link retained evidence. The Veri write-up belongs to Sahil; Sentry cannot be described as complete before the cross-track evidence gate passes.
- G2 remains outside this hardening work.
- `low_block_rate` retains the existing `low` + `special_low` definition. Agreement on narrowing it to the detector's `low` definition requires a separate coordinated metric change and calculation-version bump.

## Integration

Use [the checked-in synthetic bundle](../data/samples/synthetic/README.md) for an explicitly synthetic three-round walkthrough. Source files and schemas remain authoritative. Restart analytics and any importer to use version 3; run the importer backfill before relying on old aggregate results. Run team status before integration. The last refreshed status found new owner work on Sahil's and Garrett's branches, with no merge conflicts; it was inspected without merging it into this working tree.
