# Kumite mock servers

All three Kumite APIs, served from recordings, so the app and the replay service can be built without the game. Shapes follow `contracts/api.md` and `contracts/*.schema.json`.

## Run

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r tools/mock/requirements.txt
./tools/mock/up.sh
```

You should see:

```
1 session(s) loaded; default stream: 2026-10-17T21-13-10_sahil_djin_vs_kaz
brain     http://localhost:8765
replay    http://localhost:8766
analytics http://localhost:8767
```

`curl localhost:8765/health` → `{"ok":true,"service":"brain","version":"mock-<sha>","mock":true}`

## What it serves

By default, every recording in `data/samples/*.jsonl` (each paired with its `<name>.session.json`), plus `DATA_DIR/recordings/*.jsonl`. `DATA_DIR` defaults to `./data`.

| Port | Routes | Mock behavior |
|---|---|---|
| 8765 brain | `GET /sessions`, `/sessions/{id}`, `/sessions/{id}/recording`, `/profiles/{player}`, `GET`/`POST /config` | from the recordings; `POST /config` merges a partial body and returns 422 if the result breaks `config.schema.json` |
| 8765 brain | `WS /ws/state` | the default session's `state` and `event` lines at 60 per second, looping; `?session=<id>` picks another |
| 8765 brain | `WS /ws/coach` | at each round end of the same loop: a `round_summary`, then `{"t":"coach", ...}` text |
| 8766 replay | `POST /coach/round`, `POST /analyze/{id}`, `GET /reports/{id}`, `POST /coach/chat` | template text and a simple report (written to `DATA_DIR/reports/`); real scoring comes from Garrett's service |
| 8767 analytics | `GET /stats/{id}`, `/trends/{player}/{character}`, `/learning/{id}` | counts from the events and the learning lines |

Every service has `GET /health`, and CORS is open.

## Flags

- `--recording PATH`: serve only these recordings (repeatable).
- `--rate N`: WebSocket frames per second (default 60).
- `--no-loop`: end the streams after one pass.
- `--skip brain|replay|analytics`: free that port for the real service, e.g. `--skip analytics` while `./analytics/up.sh` runs.
- `--host`: bind address (default `0.0.0.0`, so teammates can connect by LAN IP).
- `--no-synthetic`: don't generate the synthetic session.

## Notes for clients

- Frame numbers don't start at 0 in practice recordings (practice mode doesn't reset the round counter).
- `frame_advantage` on events is from the actor's (attacker's) side.
- `/ws/state` can drop frames; events are never dropped.
- Sahil's practice recording has Sahil attacking a dummy, so its stats and report are mostly empty. The synthetic session has the full multi-round story.

## Tests

```
python -m unittest discover -s tools/mock/tests
```
