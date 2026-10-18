# B4: real live-learning sample intake

Verified October 17, 2026 PDT on local baseline `a360f8d`. M3 sample producer commit: `23eb63e` on main. Source: `data/samples/live_learning/README.md`, read before verification. Session: `2026-10-18T05-14-03_sahil_djin_vs_kaz`.

This is a real L3 versus set with human Devil Jin in slot 0 and bot Kazuya in slot 1, result **loss 1–3**. It is distinct from the generated synthetic walkthrough. Source recordings, metadata, learning and profile were not rewritten.

## Local evidence

Frozen contract examples, the full recording, all four learning records, session metadata and the supplied profile validate. File-backed `/health`, `/stats`, `/learning` and `/trends` return 200. Mock analytics matches the real stats, learning and trends; completed-round importer preparation produces four summaries, four learning records and four calculated-round rows with a source-matching final trend snapshot.

| Evidence | Verified result |
| --- | --- |
| Recording | 10,080 states, 238 events, 8 plans, 351 tactical records, 4 round summaries, 2 learning events |
| Tactical records | 231 non-reflex decisions plus 120 reflex records; 33 habit-driven decisions |
| Low contacts on human | 16 plain lows connected, zero blocked; `/stats` low-block rate 0 |
| Low picks by round | 6, 8, 8, 17; all 17 round-4 low picks use `source=habit` |
| Low-defense detection | Round 3 |
| Accuracy by round | 0.6000, 0.7333, 0.9048, 1.0000 |
| First fixed milestone | `after_block:any`, round 2 |
| Recorded fixed event | `after_block:any`, round 2, frame 1804, mastery 0.873 |
| Recorded regressed event | `after_block:any`, round 3, frame 342, mastery 0.256 |
| Round summary alignment | `newly_fixed` in round 2 and `regressed` in round 3 name `after_block:any` |
| Low-defense mastery | Never fixed; no `time_to_mastery:low_defense` value |
| Final low learning observation count | Producer reports `n=15`, separately from the 16 raw low contacts |
| Human round wins | 1; per-session round win rate 0.25 |
| Fine-tune evidence | `before=null`, `after=null`; no eval artifact supplied |

Prediction accuracy is the producer's recorded online per-round value. It is not a held-out Laya fine-tune comparison. First mastery remains recorded after later regression; current round-4 `after_block:any.fixed` is false. The low habit was detected and exploited in this set, not fixed.

The complete analytics suite ran **94 tests: 93 passed, one opt-in cloud test skipped**. The mock suite passed **46/46**. Both actual-port live-sample smoke checks passed and their servers shut down. These suite counts describe the local run. After explicit owner upload approval, the cloud backfill and aggregate/API parity checks below also passed.

## Repeat local verification

```sh
.venv/bin/python -m unittest discover -s analytics/tests -p test_live_learning.py -v
.venv/bin/python analytics/tests/live_learning_smoke.py
```

Expect five regression tests to pass, then two `PASS` lines from the smoke. The smoke needs free loopback ports 8765–8767, starts real analytics alongside mock brain/replay, exercises HTTP/catalogue and both WebSocket streams, and shuts down its processes. It explicitly clears `DATABASE_URL` and `SENTRY_DSN`: no cloud upload or telemetry is part of this local check.

For the app's analytics endpoint alone:

```sh
DATA_DIR=./data/samples/live_learning DATABASE_URL= SENTRY_DSN= .venv/bin/python -m uvicorn analytics.main:app --host 127.0.0.1 --port 8767
```

Point the existing app at :8767 and use this session id. Mocks can use the same `DATA_DIR`. Do not seed an eval file with example values for this real recording.

## Completion boundaries

- **Local B4 intake verified:** schemas, source counts, metrics, mock parity, completed-round preparation and actual-port HTTP/WebSocket playback.
- **Cloud B4 intake verified after approval:** the owner explicitly approved upload. Four completed rounds were imported into the configured Tiger Data store; the immediate repeat imported zero/found four unchanged. Stored/calculated rows and aggregate-backed API responses match the local sample. Details follow below.
- **Deliberate re-test reporting remains unverified:** the two source events establish a fixed/regressed transition for `after_block:any`. They do not identify deliberate probe attempts or demonstrate a low-defense fix. `learning_event` remains an unknown recording extension for analytics ingestion, preserved in the original file; the existing endpoint uses the four companion learning records and stats uses the summaries.
- **B5/B6 remain separate:** this is replayed data, not a live brain API session or proof of cross-service Sentry traces, native Windows behavior, or final owner visual integration.

## Approved cloud verification — October 17, 2026 PDT

The owner explicitly replied **"you may upload"** after the initial approval-review rejection. That authorized this session's frames/events, summaries and learning metrics to the existing configured Tiger Data store. Discovery was restricted to `data/samples/live_learning/` and asserted to contain exactly this one session. No profile or eval artifact was uploaded.

Baseline `a360f8d`, calculation version **4**:

| Check | Measured result |
| --- | --- |
| First backfill | `imported=4 unchanged=0 invalid_sessions=0` |
| Immediate repeat | `imported=0 unchanged=4 invalid_sessions=0` |
| Stored frames | 10,080 |
| Stored events | 238 |
| Stored round metrics | 12: four summaries, four learning records, four calculated rounds |
| Round checkpoints | Rounds 1–4 match local preparation fingerprints |
| Calculated round payloads | All four exactly match local calculations |
| Aggregate | Source signature and all 28 final metric values match file trends |
| Aggregate route proof | Real `TigerRepository` and FastAPI routes pass while the hybrid file trend reducer raises if called |
| API responses | Health, stats, learning, trends and `?stat=low_block_rate`: HTTP 200 |
| Other sessions | All four pre-existing other-session round fingerprints unchanged |
| Source preservation | Recording, learning and metadata SHA-256 unchanged |

The HTTP checks use FastAPI's in-process test client against the real app and live database. The earlier loopback HTTP/WebSocket smoke is separate. Sentry telemetry was disabled for these checks; no existing server or watcher was restarted. No schema reset or recreation was required. The importer keeps the existing unknown-record policy, so the two free-form `learning_event` records remain in the source recording rather than becoming database event rows.

A credential-free machine-readable result is retained locally at gitignored `data/verification/live-learning-cloud.json`. Credentials were read privately from the process or ignored `analytics/.env` and were never printed.

With the existing `DATABASE_URL` configured, repeat:

```sh
.venv/bin/python -m analytics.tigerdata backfill --data-dir ./data/samples/live_learning
```

With unchanged input expect `imported=0 unchanged=4 invalid_sessions=0`. The service must still use `DATA_DIR=./data/samples/live_learning`; this upload does not change its file-backed authoritative session catalogue. Low-defense mastery remains absent and fine-tune values remain null.

## Source identity

SHA-256, relative to `data/samples/live_learning/`:

| File | SHA-256 |
| --- | --- |
| `recordings/2026-10-18T05-14-03_sahil_djin_vs_kaz.jsonl` | `d80b76b456a7655f32539d24981d7c552458858d198f562426a75065c71857be` |
| `learning/2026-10-18T05-14-03_sahil_djin_vs_kaz.jsonl` | `bff4f40caa3fd36daf8b2b7bab6102ad1bf3a8c94bec57c2e4ba660807009b2f` |
| `sessions/2026-10-18T05-14-03_sahil_djin_vs_kaz.json` | `b6e3da28f8436ab51366644f781ddb1653999fc0a6cb008118c868d2e4830cd0` |
