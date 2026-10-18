# Kumite mock servers

Brain, replay and analytics APIs backed by recording files, for developing clients without Tekken. The servers consume the frozen formats in `contracts/api.md` and `contracts/recording.md`. They do not import or run `synth.py`, and need no credentials or external services.

## Run

From the repository root:

```sh
source .venv/bin/activate
python -m pip install -r tools/mock/requirements.txt
python tools/mock/serve.py --recording data/samples/practice_djin_vs_kaz.jsonl
```

Expected: one selected session, then brain on `127.0.0.1:8765`, replay on `127.0.0.1:8766`, and analytics on `127.0.0.1:8767`. `curl http://localhost:8765/health` returns `{"ok":true,"service":"brain","version":"<git sha>"}`. Each service exposes health and allows the desktop app through CORS. Ctrl-C stops all three.

For the real analytics service alongside mock brain/replay:

```sh
python tools/mock/serve.py --recording data/samples/practice_djin_vs_kaz.jsonl --services brain,replay
```

The launcher checks all requested ports before serving. An occupied port fails startup with the service and port in the error; it does not stop the process already using that port.

## Input files

`DATA_DIR` defaults to the repository's `data/`. Without `--recording`, discover `data/samples/*.jsonl` and `DATA_DIR/recordings/*.jsonl`. Metadata files in `DATA_DIR/sessions/` also index their existing recording references. Relative recording references resolve from the repository root.

Each recording needs metadata from `<recording-stem>.session.json`, or `DATA_DIR/sessions/<session_id>.json`. Missing or invalid required files fail with a diagnostic. The id comes from the records, not the filename. The shipped sample is named `practice_djin_vs_kaz.jsonl`, but its id is `2026-10-17T21-13-10_sahil_djin_vs_kaz`.

Optional files are `DATA_DIR/learning/<session_id>.jsonl`, `profiles/*.json`, and `reports/<session_id>.json`. Learning records embedded in a recording take precedence over its learning file. Missing learning returns empty rounds/maps and null fine-tune values; missing profiles returns an empty list. Known records and schema-backed responses are validated. Unknown fields are retained, unsupported record types are ignored by playback, and an incomplete final JSON line is tolerated. Malformed complete lines fail with a filename and line number.

## APIs and mock behavior

| Service | Routes | Behavior |
|---|---|---|
| Brain :8765 | `/sessions`, `/sessions/{id}`, `/sessions/{id}/recording` | Sessions newest first; recording download preserves original bytes and uses `application/x-ndjson`; unknown ids return 404 |
| Brain :8765 | `/profiles/{player}`, GET/POST `/config` | Loaded profiles; in-memory config initialized for the selected session; recursive partial updates validated before storage |
| Brain :8765 | WebSockets `/ws/state`, `/ws/coach` | Shared replay timeline per session; state/events and round summaries with canned coach text |
| Replay :8766 | POST `/coach/round`, `/coach/chat` | Deterministic template coaching; chat cites only moments from the selected recording |
| Replay :8766 | POST `/analyze/{id}`, GET `/reports/{id}` | Mock analysis persisted under `DATA_DIR/reports/`; 404 before analysis unless saved; unknown ids return 404 |
| Analytics :8767 | `/stats/{id}`, `/trends/{player}/{character}`, `/learning/{id}` | Simple event-derived placeholder stats, sorted trends with optional `?stat=`, and available learning records |

Coaching and option scores are canned mock content. Stats use provisional event heuristics, including the assumption that event frame advantage is from the actor's side; these are not the real analytics pipeline or verified coaching. The real practice sample lacks round summaries and learning data. For playback, a minimal summary is derived at the last frame of each round, with no invented mastery/habit claims. Richer learning curves require a recording and learning files containing them.

Playback advances at 60 game frames per second, preserving frame gaps and source order. It handles nonzero initial frames, frame resets at round boundaries, and EOF looping. All sockets for a session join the same running timeline. Slow clients may miss state messages; a client that cannot accept required events or summaries is explicitly disconnected rather than silently losing those records. Reconnect joins the current position. The mock is a recording snapshot; restart to reload a changed streamed recording.

## Flags

- `--recording PATH`: select a recording, repeatable; the first is the default stream. Other sessions indexed through metadata remain available by id.
- `--services brain,replay,analytics`: choose services to run; default is all three.
- `--skip analytics`: compatibility shorthand for omitting a service; repeatable.
- `--host 0.0.0.0`: allow LAN clients; default is loopback only.
- `--rate N`: positive game frames per second; default 60.
- `--no-loop`: end WebSockets at EOF. Connections after EOF close immediately; restart to replay again.

WebSockets accept `?session=<id>` to select another loaded session. Unknown ids close with code 1008. Slow clients close with code 1013.

## Verification

```sh
python contracts/validate.py
python contracts/validate.py data/samples/practice_djin_vs_kaz.jsonl
python contracts/validate.py tools/mock/tests/fixtures/two-rounds.jsonl
python -m unittest discover -s tools/mock/tests
python tools/mock/tests/smoke.py
```

Expected: validators print `PASS`, unit tests pass, and the smoke script prints two `PASS` lines. The smoke test needs free local ports 8765–8767 and runs the actual launcher, HTTP APIs, WebSockets, occupied-port handling, and SIGINT shutdown. It uses temporary storage and stops its servers afterward. The small two-round test fixture is independent of the generator and covers frame resets, unknown fields/types, summaries and learning records.

When section 3.1 produces another recording, select its JSONL with `--recording`; provide its companion metadata and learning file in the documented locations. No server changes are needed.

## Synthetic session (section 3.1)

`python tools/mock/synth.py` writes a seeded three-round Devil Jin (human) vs Kazuya (bot) session to `DATA_DIR`: `recordings/`, `sessions/`, `learning/` and `profiles/`. It isn't committed (about 7 MB); the same seed gives the same file everywhere. The servers load it automatically from `DATA_DIR`, and it streams with `ws://localhost:8765/ws/state?session=2026-10-17T13-05-00_synth_djin_vs_kaz`.

| Round | What happens (real Kazuya move ids) | Learning line | Winner |
|---|---|---|---|
| 1 | df+1 blocked, then d+4 low hits 4 of 5; one throw lands, one is broken | accuracy 0.41, `low_defense` p 0.8, mastery 0.22 | bot |
| 2 | lows hit 3 of 5; a df+2 mid catches a duck | accuracy 0.58, mastery 0.55 | bot |
| 3 | every low blocked and punished; the plan switches to mids and throws | accuracy 0.71, `low_defense` fixed, `player_changed` | human |

Result `loss 1-2`; `/learning` gives `time_to_detect.low_defense = 1` and `time_to_mastery.low_defense = 3`. Flags: `--seed`, `--rounds` (1–3), `--round-seconds` (30 minimum), `--player`, `--out`. Tests: `tests/test_synth.py`.
