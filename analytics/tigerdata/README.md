# Tiger Data integration

Tiger Data stores completed rounds and supplies `/trends` through a continuous aggregate. File-backed `/stats` and `/learning` keep their existing behavior. The importer runs separately from the game and API; no request writes to the database.

## Configure and run

From the repository root, with `DATABASE_URL` exported in this terminal:

```sh
source .venv/bin/activate
python -m pip install -r analytics/tigerdata/requirements.txt
python -m analytics.tigerdata init
python -m analytics.tigerdata backfill --data-dir ./data
python -m analytics.tigerdata watch --data-dir ./data
```

Use the Tiger Data cloud service's TLS-enabled connection string. Keep credentials out of source control and shared transcripts. The CLI reads the process environment and deliberately does not source `.env` files. Missing `DATABASE_URL` exits with code 2.

For the API, put `DATABASE_URL` in the existing gitignored `analytics/.env`, or export it before starting `analytics/up.sh`. To load that file for CLI commands in your own terminal:

```sh
set -a
source analytics/.env
set +a
```

`init` explicitly creates or upgrades only the `kumite` schema. Run it again after this update: it adds the fourth hypertable, publication checkpoint table and continuous aggregate to the earlier three-hypertable foundation. It requires TimescaleDB 2.13+ and creation permissions. Initialization is repeatable and never happens during API startup. It does not create the extension or cloud service.

`backfill` reports imported/unchanged rounds and invalid sessions. Exit code 0 means the scan completed without detected errors; code 1 means a failure occurred. Already committed rounds survive later failures. The first import after this update reimports existing rounds to add calculated stats.

`watch` scans every two seconds after work completes. Database failures produce credential-free warnings and retry on later scans. Ctrl-C exits normally. You can stop it whenever automatic uploads are unnecessary; a later backfill catches up. Keep the analytics server running while the app needs its endpoints. Neither process requires the other to stay alive.

## Storage and calculations

| Object | Contents |
|---|---|
| `sessions` | Canonical session metadata, start time and original JSONB |
| `frames` | State hypertable, one row per source state |
| `events` | Event hypertable, preserving distinct same-frame events |
| `round_metrics` | Hypertable containing original summaries/learning plus `kind=calculated_round`, `source=calculated` statistics from `analytics.stats.compute` |
| `ingest_rounds` | Content fingerprint and import checkpoint per session/round |
| `trend_snapshots` | Hypertable of cumulative session metric snapshots after each completed round |
| `session_trends` | Daily continuous aggregate: latest snapshot value per session and metric |
| `trend_imports` | Source fingerprint, expected metric count, refresh window and publication readiness |

Raw records preserve unknown fields in JSONB and promote session/round/frame, player, character, difficulty, source and physical source-line identifiers. Calculated rows use source line 0. Learning records have no promoted frame; extension fields remain untouched in JSONB.

`observed_at` estimates elapsed game time: session start plus cumulative recorded round durations and frame offsets at 60 FPS. Nonzero initial counters and round resets are supported. Each next round begins one frame after the prior recorded round ends. Frameless summaries and learning use the round's last observed frame. Between-round delays are unknown; this is not measured wall-clock timing. Original frame counters remain stored.

Unique keys include the timestamp partition dimension, as required by [TimescaleDB hypertable constraints](https://www.tigerdata.com/docs/reference/timescaledb/hypertables/create_hypertable). SQL identifiers are quoted and values are bound.

Completed-round statistics reuse the real analytics reducer, including actor-relative advantage, the provisional punish allowance, actual tracker throw conventions and state-derived damage situations. Trend snapshots reuse `analytics.metrics.trend_values` and the validated learning loader, so flattened keys, null rates, authoritative first mastery and difficulty-specific win rates match the file endpoint. Companion learning files supply historical learning; inline learning records remain raw evidence only.

Snapshots contain cumulative measurements within one session. The [continuous aggregate](https://www.tigerdata.com/docs/build/continuous-aggregates/create-a-continuous-aggregate) groups by `time_bucket('1 day', observed_at)`, session and metric, using `last(value, observed_at)`. Reads choose the latest bucket per metric. Rates are calculated from session events before storage, never averaged between rounds or sessions. This also preserves nulls and the last available habit observation.

## Imports, corrections and publication

Discover canonical `sessions/*.json` and paired `samples/*.session.json` / `.jsonl`, preferring canonical metadata. Canonical recording references resolve from the repository root; absent references use `recordings/<id>.jsonl` with paired-sample fallback. Read companion `learning/<id>.jsonl` and optional `eval/<id>.json`. Producer files are never modified.

Validate recognized records against the frozen contracts, preserve unknown fields, ignore unsupported types and tolerate an incomplete trailing JSONL object. Malformed complete records or mismatched ids identify the affected session/file. An invalid session is skipped; invalid discovery metadata aborts that scan.

Only a recorded `round_end` or round summary closes a round. Active rounds remain untouched. Each completed round transaction replaces changed raw/calculated rows and updates its fingerprint checkpoint. Unchanged rounds are skipped. Corrections, late learning and changed prior-round durations invalidate affected imports. A failed transaction restores previous rows and checkpoints.

After round ingestion, a separate transaction replaces that session's trend snapshots and marks its publication unavailable. A session advisory lock serializes publishers. The importer explicitly refreshes the complete old/new UTC bucket range, then marks the source revision ready. A crash or refresh failure leaves the API on files; a later scan retries. This avoids exposing an outdated aggregate as a newly imported revision. Calculations check that source files and metadata stayed stable during preparation.

## API selection and offline behavior

When `DATABASE_URL` is set, `/trends` tries the aggregate for the locally discovered matching sessions. The local session catalogue remains authoritative, including exact player/character matching and chronology. Keep local recording files; this is not a cloud archive browser.

The API compares a content fingerprint of canonical metadata, recording, companion learning and optional evaluation input. It checks file modification time and size on each request and caches unchanged file hashes. Only a ready aggregate with a matching fingerprint and expected metric count is used. Missing imports, active rounds, late data or corrected files fall back to the existing file reducers per session. This keeps the current live timeline visible while ingestion catches up. Invalid local data still produces the existing 503 diagnostic.

Without `DATABASE_URL`, the API serves files. Database connection/query failures warn without credentials and use files; attempts resume after a two-second cooldown. No schema initialization, backfill, aggregate refresh or database writes happen in the API process. `/health`, CORS and the single Sentry initialization are retained.

## Verify

```sh
python -m pip install -r analytics/requirements-dev.txt
python -m unittest discover -s analytics/tests -v
python -m unittest discover -s tools/mock/tests -v
python contracts/validate.py
python analytics/tests/smoke.py
```

For live cloud verification, with `DATABASE_URL` in the same terminal:

```sh
TIGERDATA_RUN_INTEGRATION=1 python -m unittest discover -s analytics/tests -p test_tigerdata_integration.py -v
```

The live test creates and removes only its uniquely named `kumite_test_*` schema. It verifies four hypertables, the continuous aggregate, expected row counts, file/database trend parity, API database reads and outage fallback, repeat imports, corrections, late learning, actual constraint-triggered rollback and reconnection. A result containing `skipped=1` does not verify the database. Offline tests cover source edge cases, snapshot replacement/rollback, failed refresh retry, freshness and credential-free recovery. Cloud application and the expanded integration test must run after this schema update; prior successful tests of the foundation do not validate the new aggregate. This update was applied and verified on the configured service on 2026-10-17; see [verification results](VERIFICATION.md).
