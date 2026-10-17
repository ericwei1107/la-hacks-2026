# Recording format

Every service reads and writes under one data directory, passed as the `DATA_DIR` environment variable (default `./data`).

```
data/
  recordings/<session_id>.jsonl
  sessions/<session_id>.json
  learning/<session_id>.jsonl
  profiles/<player>_<character>.json
  reports/<session_id>.json
  samples/
```

Only `data/samples/` is committed. Everything else under `data/` is local.

## Session id

`<UTC start time as YYYY-MM-DDTHH-MM-SS>_<player>_<human character short>_vs_<bot character short>`, for example `2026-10-17T13-05-00_sahil_djin_vs_kaz`. Short names: `djin`, `kaz`, `king`, `shaheen`.

## data/recordings/<session_id>.jsonl

One JSON object per line. Every line has `t` (record type), `session_id`, and `round`; every line except `round_summary` also has `frame`.

| `t` | Written by | When | Schema |
|---|---|---|---|
| `state` | hot loop | every game frame | `gamestate.schema.json` |
| `event` | hot loop | on change | `event.schema.json` |
| `tactical` | brain | each tactical decision | free-form object: `frame`, `frame_asked`, `options`, `chosen`, `probabilities`, `source` (`laya`, `default`, `habit`) |
| `plan` | brain | each plan update | `gameplan.schema.json` plus `t`, `frame`, `round`, `session_id` |
| `round_summary` | brain | round end | `round_summary.schema.json` |

Rules:
- `frame` is the game's round frame counter (60 per second). It resets to 0 at each round start. Order within a round is by `frame`; across rounds by `round`.
- Lines are appended as they happen and flushed at least once per second. A reader must tolerate a truncated last line.
- Unknown `t` values and unknown fields must be ignored, not rejected.
- `players[i].slot` is the game's block slot, not the screen side. The human is `players[human_slot]`. Use `side` for left and right.
- Positions are millimetres. Distances in `derived.distance_mm` are horizontal (x/z only).

## data/sessions/<session_id>.json

`session.schema.json`. Written at session start, rewritten at each round end.

## data/learning/<session_id>.jsonl

One line per round, `t = "learning_round"`, matching `metrics.schema.json#/$defs/round`. Written by the brain at round end.

## data/profiles/<player>_<character>.json

`profile.schema.json`. Owned by the brain; read-only for every other service.

## data/reports/<session_id>.json

`report.schema.json`. Written by the replay service.

## Validating

```
python contracts/validate.py
python contracts/validate.py data/samples/<file>.jsonl
```
