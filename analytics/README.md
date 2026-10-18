# Analytics service

The real analytics service serves stats, learning metrics and per-session trends on port 8767. It works from files without a running game. Optional Tiger Data integration serves current trends from a continuous aggregate and falls back to files. Sentry retains HTTP transactions with loading, reduction and learning operation spans. See [remediation status and owner handoffs](REMEDIATION.md).

## Real live-learning sample

`data/samples/live_learning/` is a real L3 set, session `2026-10-18T05-14-03_sahil_djin_vs_kaz`. Set `DATA_DIR` to that folder. Detection/exploitation is measured; low-defense mastery is absent. Recorded accuracy is 0.60 → 0.7333 → 0.9048 → 1.00, and `after_block:any` has a fixed event followed by regression. Fine-tune values remain null. See [local verification and exact run commands](LIVE_LEARNING_VERIFICATION.md); approved cloud ingestion and aggregate/API parity are verified (four rounds imported; repeat imported zero).

## Run

```sh
source .venv/bin/activate
python -m pip install -r analytics/requirements.txt
DATA_DIR=./data analytics/up.sh
```

Expected: Uvicorn listens on :8767; `curl http://localhost:8767/health` returns `ok: true` and `service: analytics`. Run mock brain/replay separately with `python tools/mock/serve.py --services brain,replay`. Use `python tools/mock/synth.py` once to create the optional demo session, then query:

```sh
curl http://localhost:8767/learning/2026-10-17T13-05-00_synth_djin_vs_kaz
curl http://localhost:8767/trends/synth/devil_jin
curl 'http://localhost:8767/trends/synth/devil_jin?stat=mastery:low_defense'
```

The demo shows detection in round 1, first mastery in round 3, and per-round accuracy 0.41, 0.58, 0.71. Its per-session round win rate is 0.333.

## Learning: GET /learning/{session_id}

Responses follow `contracts/metrics.schema.json`. Read rounds from `DATA_DIR/learning/<session_id>.jsonl`; keep unknown fields, sort by round and use the last complete record when a round repeats. Detection is the first round with `n >= 4` and `p >= 0.6`. Mastery is the first round whose producer sets `fixed: true`; later regression does not erase the milestone. These times are round numbers. The service does not infer mastery or re-tests, and never uses mutable player profiles as historical evidence.

A known session with no learning file returns empty rounds/maps and null fine-tune values. An unknown session returns 404. Optional evaluation results live in `DATA_DIR/eval/<session_id>.json`:

```json
{"before": 0.41, "after": 0.68}
```

Both keys are required when the file exists; each is null or a finite number between 0 and 1. The evaluation harness can write this file later; missing files return both values as null. Inline extra fields on learning records do not supply evaluation results.

## Trends: GET /trends/{player}/{character}

Match player and human character exactly; include synthetic sessions if they match. Each point describes one session, rather than cumulative history. Return `player`, `character`, and `series`, where each point contains `session_id`, `started_at`, and flat numeric-or-null `values`. Sort by the parsed timestamp, then session id. No matches returns an empty series.

| Values key | Meaning |
|---|---|
| `punish_rate`, `throw_break_rate`, `low_block_rate`, `counter_hits_taken`, `counter_hits_given`, `avg_adv_after_block`, `rounds_won` | Per-session event totals/rates |
| `damage_taken_by_situation:<situation>` | Human damage taken from hits, counter-hits and throws, grouped by situation; missing situations use `neutral` |
| `throw_breaks_by_type:<input>` | Successful human breaks by input |
| `habit_probability:<habit>` | Last available recorded habit probability in this session |
| `mastery:<habit>` | Last available recorded mastery probability in this session |
| `time_to_mastery:<habit>` | First fixed round in this session |
| `win_rate:difficulty:<difficulty>` | Human rounds won divided by decided rounds in this session |

`?stat=<name>` selects exactly one key. Points without that key remain in the series with empty `values`. Unavailable dynamic metrics are omitted; rates without observations are null. Regressed habits retain their first mastery milestone but show their latest mastery probability.

Event calculations preserve the existing mock reducer conventions: frame advantage is actor-relative; a punish opportunity requires a blocked bot move at -10 or worse, and a human hit/counter-hit in the same round within `abs(frame_advantage) + 10` frames. The extra 10-frame allowance is provisional. Throw-break rate follows the real tracker: human breaks divided by bot throws on the human, capped at 1. The tracker records every throw and emits an additional break event when it is broken.

Round winners start with metadata and are updated by non-null recorded round-end events/summaries in file order. One hit can satisfy only the most recent unmatched qualifying punish opportunity in the same round. Unknown winners do not enter the denominator. The service does not aggregate match win rates across sessions or difficulties.

## Stats: GET /stats/{session_id}

Per-round blocks plus `totals`, in the `contracts/api.md` shape, computed by `analytics/stats.py` from the session's recording. The mock's `/stats` uses the same reducer. Mock and real trend/learning derivation and evaluation validation also share implementations. Rates are 0–1, or null when the situation never happened.

| Field | Meaning |
|---|---|
| `damage_taken_by_situation` | damage from `hit`/`counter_hit`/`throw` on the human, keyed by the event's `situation`, else the brain's `derived.situation` at that frame, else `neutral` (real events carry no `situation`) |
| `punish_rate` | blocks of a bot move at frame advantage ≤ −10 (the actor's advantage) that the human punished with a hit within `abs(advantage) + 10` frames |
| `throw_break_rate` | human `throw_break` events ÷ bot `throw` events on the human; the real tracker emits `throw` for every throw and adds `throw_break` when it's broken |
| `low_block_rate` | bot lows (`hit_level` `low`) on the human: blocked ÷ blocked + hit. Special lows are excluded: they're stand-blockable, so they don't test the crouch-block habit, and this matches `game/detect.py`'s `low_defense` |
| `counter_hits_taken`, `counter_hits_given` | counter hits with the human as target / actor |
| `avg_adv_after_block` | mean frame advantage from the human's side after blocking |
| `rounds_won` | extra: 1/0/null per round; the human's wins in `totals` |
| `throw_breaks_by_type` | extra: the human's breaks by input (`press_1`, …) |

Top-level extras: `health_timeline` (`{round: [[frame, human_hp, bot_hp], ...]}`, every 30 frames plus each round's last frame) and `skipped_lines` (unreadable or schema-invalid recording lines). Unsupported record types are ignored before reduction and do not create rounds.

Recordings grow during live play, so `/stats` parses newly appended complete lines after verifying the previously consumed byte prefix whenever the file changes. A partial last line waits until it's complete; a changed inode, shorter file or modified consumed prefix resets the reader, including larger replacements and in-place corrections. Prefix verification reads old bytes without reparsing their records. Unlike `/learning` and `/trends`, an unreadable line in a recording is skipped and counted in `skipped_lines` rather than failing the request, so one bad write during a live set doesn't take the panel down. Unknown session: 404.

## Files, refresh and failures

Discover canonical metadata in `DATA_DIR/sessions/*.json` and paired `DATA_DIR/samples/<name>.session.json` / `<name>.jsonl` samples. Canonical metadata wins for duplicate session ids. Recording references in canonical metadata resolve relative to the repository root, or may be absolute. Without a reference, use `DATA_DIR/recordings/<session_id>.jsonl`, falling back to its paired sample if available. Session ids come from metadata, not the sample filename.

Each request checks modification time and size of relevant metadata, recording, learning and evaluation files. Unchanged parsed data and derived results are cached; changed or removed files invalidate affected results. Recording data is needed for trends, not for learning. Unknown recording types are ignored and recognized records use the frozen schemas. Invalid metadata is isolated: unrelated sessions remain available and requesting the invalid session returns 503. An incomplete final JSONL record without a newline is tolerated; malformed complete records fail.

Invalid required data or an invalid optional file that exists returns HTTP 503 with a concise diagnostic and an error log. Missing optional learning/evaluation files are unavailable data, not zero measurements. No files are repaired or fabricated. With `DATABASE_URL`, the repository reads ready, source-matching Tiger Data trend aggregates and uses files for missing/stale imports or database outages. Stats and learning continue reading files. API database connections/statements each have two-second limits; the importer keeps longer limits. Database I/O releases the shared file lock, so stats and learning remain responsive and other trend requests can fall back without waiting. Database failures log a credential-free warning and retry after two seconds. Calculation version 4 invalidates older round/aggregate fingerprints and counts only plain lows; restart and backfill after upgrading. See [Tiger Data setup](tigerdata/README.md) for explicit schema initialization, backfill, watcher lifecycle and cloud verification commands.

## Optional session archive (B8)

Install `analytics/requirements-archive.txt`, then run `python -m analytics.archive --data-dir ./data` to write local, compressed `data/archive/<session_id>.parquet` snapshots from JSONL and zipped recordings. See the [implementation plan, SQL examples and optional backup commands](ARCHIVE.md). Archive dependencies are separate from the analytics service.

## Verify

```sh
python -m pip install -r analytics/requirements-dev.txt
python -m unittest discover -s analytics/tests -v
python -m unittest discover -s tools/mock/tests -v
python contracts/validate.py
python analytics/tests/smoke.py
```

The analytics tests cover reducer calculations, schema validity, thresholds, regression, duplicate rounds, file changes, filtering, ordering and unavailable data. The smoke script requires free ports 8765–8767, generates data in a temporary directory, starts real analytics alongside mock brain/replay, exercises both endpoints and live evaluation refresh, and stops its servers afterward. It disables Sentry only in those test subprocesses.

## Checked-in walkthrough

Use [data/samples/synthetic](../data/samples/synthetic/README.md) for the reproducible three-round fixture and exact two-terminal commands. Its planted learning values are synthetic. No fine-tune improvement is fabricated. Health returns the Git SHA; Sentry uses its separate release identifier.
