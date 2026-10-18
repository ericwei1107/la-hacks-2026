# Tiger Data verification — 2026-10-17

## B3: calculation version 4 refresh

Completed on 2026-10-18 UTC (2026-10-17 PDT) using `Eric` at `58ff04a`.
The [implementation plan](B3-PLAN.md) preceded the run. PR #8 was confirmed open;
the refresh used its existing branch implementation without merging it. No
runtime code, schema or frozen contract changes were necessary.

Before writing, all four stored round checkpoints matched locally prepared
version **3** fingerprints and none matched version **4**. A repeatable-read,
read-only transaction captured the seven application tables and the materialized
`session_trends` rows as a private logical JSONL snapshot:

- Local, gitignored file: `data/tigerdata-backups/20261018T032843Z-kumite-before-v4.jsonl`
- Size: 9,930,914 bytes; permissions: directory `0700`, file `0600`.
- SHA-256: `0d7f978e2c06d66df62cdccaeccaab160ff70c679e4f444daa2e230b72f91c55`
- This is a table-tagged row snapshot requiring the existing schema, not a full
  PostgreSQL backup. Original recordings and metadata were preserved.

Explicit `init` succeeded. The first `backfill --data-dir ./data` reported
`imported=4 unchanged=0 invalid_sessions=0`; its immediate repeat reported
`imported=0 unchanged=4 invalid_sessions=0`. Both exited 0. All four resulting
checkpoint fingerprints and calculated-round JSON payloads matched version 4
preparation. Both published aggregate signatures and every metric matched the
file reducer.

| Relation | Rows before and after |
|---|---:|
| `sessions` | 2 |
| `ingest_rounds` | 4 |
| `frames` | 5,986 |
| `events` | 100 |
| `round_metrics` | 10 |
| `trend_snapshots` | 62 |
| `trend_imports` | 2 |
| `session_trends` | 27 |

The cloud catalogue retained these existing, locally discoverable sessions:

| Session | Completed rounds | `low_block_rate` |
|---|---|---:|
| `2026-10-17T13-05-00_synth_djin_vs_kaz` | 1, 2, 3 | 0.533 |
| `2026-10-17T21-13-10_sahil_djin_vs_kaz` | 1 | null |

These two rate values happen to equal their version 3 values; the refreshed
fingerprints and calculated-row comparisons establish the recomputation. No
ZIPs were extracted and no additional nested synthetic fixtures were added to
the catalogue. Synthetic data remains labelled `player=synth`; Sahil's real
practice session remains `player=sahil`.

An actual temporary Uvicorn server on loopback port **53104** used the configured
cloud database. `/trends/sahil/devil_jin`, `/trends/synth/devil_jin`, and both
`?stat=low_block_rate` requests returned 200 and exactly matched `FileRepository`.
During these HTTP checks the hybrid repository's file trend reducer was patched
to raise, proving that published aggregates supplied the responses. Health,
stats and learning also passed against file expectations. The temporary server
shut down cleanly; no existing API or watcher process was restarted.

Validation:

- Opt-in live integration: **1 passed, no skips** (6.878 seconds), including four
  hypertables, continuous aggregate reads, repeat initialization/imports,
  corrections, late learning, outage fallback, constraint-triggered rollback and
  reconnect. The uniquely named test schema was removed by its cleanup.
- Analytics regression suite: **73 tests, 72 passed, 1 expected live-test skip**
  (21.941 seconds). The live test passed separately as described above.
- `contracts/validate.py`: **PASS**, all nine frozen examples.

Credentials were loaded privately from ignored `analytics/.env` and were never
printed. Reproduce the unchanged import and cloud integration test from the
repository root:

```sh
set -a
source analytics/.env
set +a
.venv/bin/python -m analytics.tigerdata backfill --data-dir ./data
TIGERDATA_RUN_INTEGRATION=1 .venv/bin/python -m unittest discover -s analytics/tests -p test_tigerdata_integration.py -v
```

With the same input, expect `imported=0 unchanged=4 invalid_sessions=0`, followed
by one live test with `OK` and no skipped marker. Restart any older long-lived
API/watcher processes to load calculation version 4. Local source files remain
necessary for catalogue and freshness checks. B4's future learner samples and
B1's mock ZIP support remain separate batches.

## Calculation version 3 remediation

Verified baseline commit `e876d8b` plus the remediation working-tree changes. The opt-in live integration test passed in its disposable schema, proving aggregate-backed reads while `trend_values` is patched to fail, as well as correction replacement, outage fallback, rollback and reconnect. The test removed its schema afterward.

Backfill on the configured `kumite` schema rebuilt four completed rounds: `imported=4 unchanged=0 invalid_sessions=0`. Immediate repeat: `imported=0 unchanged=4 invalid_sessions=0`. Both import and aggregate fingerprints now include calculation version **3**; existing API/watcher processes must be restarted to load it. Credentials were loaded privately from ignored `analytics/.env` and were not printed.

The delayed-database regression verifies that pending database work does not block stats, learning, or a second file-fallback trend request. API connection/statement limits are two seconds each; importer limits remain longer. The loopback smoke verifies real analytics with mock brain/replay, eval refresh and clean shutdown. It is separate from the live cloud test.

## Earlier integration verification

The updated schema was applied to the configured cloud service through `analytics/.env`; credentials were neither printed nor committed.

- Explicit `init` succeeded, including four hypertables and `session_trends` continuous aggregate.
- Backfill imported 4 completed rounds with no invalid sessions. Repeated backfill reported `imported=0 unchanged=4 invalid_sessions=0`.
- The opt-in live integration test passed without skipping. Its temporary schema verified repeated initialization, four hypertables, the aggregate, expected raw/calculated row counts, aggregate/file parity, database repository reads, outage fallback, corrected-round replacement, late learning, actual constraint-triggered rollback, and disconnect/reconnect recovery. The temporary schema was removed afterward.
- The actual analytics server ran with the configured Tiger Data connection on temporary port 18768. Health, stats and learning returned 200; trends matched file results. It shut down cleanly.
- Local analytics suite: 62 cases, 61 passed and the opt-in cloud case skipped in that run; the cloud case subsequently passed separately. Mock suite: 34 passed. Frozen contract examples and the real sample validated. Real analytics alongside mock brain/replay passed the temporary-data smoke test and shut down cleanly.

Reproduce the cloud test from a terminal with `DATABASE_URL` configured:

```sh
TIGERDATA_RUN_INTEGRATION=1 .venv/bin/python -m unittest discover -s analytics/tests -p test_tigerdata_integration.py -v
```

Expected: one live test passes with `OK`, without a skipped marker. The watcher and API are independent; stopping the watcher pauses uploads until the next backfill or watcher run. Local files remain required for the API's authoritative session catalogue and freshness checks.
