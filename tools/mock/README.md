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

To discover the shipped practice and two zipped versus sessions automatically:

```sh
python tools/mock/serve.py --services brain,replay
curl http://localhost:8765/sessions
```

Expected: three shipped sessions, plus any local recordings indexed under `DATA_DIR` (four when the synthetic session has been generated there). Sessions are listed newest first; the neutral versus session `2026-10-18T01-24-57_sahil_djin_vs_kaz` is the default with the shipped samples. Its state stream is `ws://localhost:8765/ws/state?session=2026-10-18T01-24-57_sahil_djin_vs_kaz`.

Select one archive explicitly with `python tools/mock/serve.py --recording data/samples/versus_djin_vs_kaz_l3.zip --services brain,replay`. The first `--recording` is the default stream even when other indexed sessions are newer.

The launcher checks all requested ports before serving. An occupied port fails startup with the service and port in the error; it does not stop the process already using that port.

## Input files

`DATA_DIR` defaults to the repository's `data/`. Without `--recording`, discover `.jsonl` and `.zip` files in `DATA_DIR/samples/` and `DATA_DIR/recordings/`. Metadata files in `DATA_DIR/sessions/` also index their existing recording references, including ZIP paths. Relative recording references resolve from the repository root.

Each recording needs metadata from `<recording-stem>.session.json`, or `DATA_DIR/sessions/<session_id>.json`. Missing or invalid required files fail with a diagnostic. The id comes from the records, not the filename. The shipped sample is named `practice_djin_vs_kaz.jsonl`, but its id is `2026-10-17T21-13-10_sahil_djin_vs_kaz`.

Each ZIP must contain exactly one recording `.jsonl` and its paired `<recording-stem>.session.json` in the same archive directory. Nested directories are supported. `.learning.jsonl` members are excluded from recording selection; learning continues to use external or inline records as described below. Archive metadata is validated and must match the recording's session id. Members are read directly without extracting files or following the metadata's `recording` reference. Corrupt archives, missing paired metadata, and multiple recording members fail with a diagnostic; invalid discovered archives are isolated from healthy sessions. The recording download returns the exact decompressed JSONL bytes with the same media type as an ordinary recording.

Optional files are `DATA_DIR/learning/<session_id>.jsonl`, `profiles/*.json`, and `reports/<session_id>.json`. A companion learning file takes precedence; inline learning records remain a fallback for standalone mock fixtures. Repeated round numbers use the last complete record and are sorted by round. Unknown learning extension fields are retained. Missing learning returns empty rounds/maps and null fine-tune values; missing profiles returns an empty list. Known records and schema-backed responses are validated. Fine-tune values come only from `DATA_DIR/eval/<session_id>.json`, using real analytics validation; a missing file gives nulls and an invalid existing file gives 503. Unknown fields are retained, unsupported record types are ignored by playback, and an incomplete final JSON line is tolerated. Malformed complete lines fail with a filename and line number.

## APIs and mock behavior

| Service | Routes | Behavior |
|---|---|---|
| Brain :8765 | `/sessions`, `/sessions/{id}`, `/sessions/{id}/recording` | Sessions newest first; recording download preserves original bytes and uses `application/x-ndjson`; unknown ids return 404 |
| Brain :8765 | `/profiles/{player}`, GET/POST `/config` | Loaded profiles; in-memory config initialized for the selected session; recursive partial updates validated before storage |
| Brain :8765 | WebSockets `/ws/state`, `/ws/coach` | Shared replay timeline per session; state/events and round summaries with canned coach text |
| Replay :8766 | POST `/coach/round`, `/coach/chat` | Deterministic template coaching; chat cites only moments from the selected recording |
| Replay :8766 | POST `/analyze/{id}`, GET `/reports/{id}` | Mock analysis persisted under `DATA_DIR/reports/`; 404 before analysis unless saved; unknown ids return 404 |
| Analytics :8767 | `/stats/{id}`, `/trends/{player}/{character}`, `/learning/{id}` | Shared real-analytics reducers, learning-derived trend values with optional `?stat=`, and normalized learning/eval records |

Stats, trends and learning use the real analytics calculations, including actor-relative frame advantage and the provisional punish window. Coaching and option scores remain canned content. The internal module is named `analytics_mock.py` so it cannot shadow the real analytics package. The real practice sample lacks round summaries and learning data. For playback, a minimal summary is derived at the last frame of each round, with no invented mastery/habit claims. Richer learning curves require a recording and learning files containing them.

Playback advances at 60 game frames per second, preserving frame gaps and source order. It handles nonzero initial frames, frame resets at round boundaries, and EOF looping. All sockets for a session join the same running timeline. Slow clients may miss state messages; a client that cannot accept required events or summaries is explicitly disconnected rather than silently losing those records. Reconnect joins the current position. The mock is a recording snapshot; restart to reload a changed streamed recording.

## Flags

- `--recording PATH`: select a JSONL or ZIP recording, repeatable; the first is the default stream. Other sessions indexed through metadata remain available by id.
- `--services brain,replay,analytics`: choose services to run; default is all three.
- `--skip analytics`: compatibility shorthand for omitting a service; repeatable.
- `--host 0.0.0.0`: allow LAN clients; default is loopback only.
- `--rate N`: positive game frames per second; default 60.
- `--no-loop`: end WebSockets at EOF. Connections after EOF close immediately; restart to replay again.
- `--experimental-insights`: add the unapproved `GET /insights/{id}` (public v1 view) to mock analytics, read from `DATA_DIR` with the same builder as real analytics. Off by default; sessions loaded only through `--recording` outside `DATA_DIR` return 404. Not a frozen contract.
- `--live-dir DIR`: write the default streamed session into `DIR` as it plays, so the real analytics service sees a growing session. Metadata omits end time/result; state/event lines flush once a second like the recorder; each round summary is written once and flushed; that round's original learning record follows after `--learning-delay` seconds (default 3, 0–120). Streams once (no loop). Refuses `data/samples` and the source file. Requires `--services brain,replay` with the real analytics service on `DIR`.
- `--duplicate-summaries`: send every round summary twice on `/ws/coach`, to check that clients coalesce them.
- `--drop-after-summary`: close brain sockets with code 1013 after each round's coach line, to exercise reconnects.

WebSockets accept `?session=<id>` to select another loaded session. Unknown ids close with code 1008. Slow clients close with code 1013.

## Live refresh scenario

For testing refresh without the game, in two terminals from the repo root:

```sh
DATA_DIR=./data/samples/live_learning SENTRY_DSN= .venv/bin/python tools/mock/serve.py --services brain,replay --live-dir /tmp/kumite-live --learning-delay 3
DATA_DIR=/tmp/kumite-live KUMITE_EXPERIMENTAL_INSIGHTS=1 DATABASE_URL= SENTRY_DSN= .venv/bin/python -m uvicorn analytics.main:app --port 8767
```

Expected: the brain streams the real session once at 60 frames per second (about 40 seconds per round; add `--rate 120` to halve that). `/stats` grows during each round. At each round end `/insights/<id>` reports `quality: "pending"` with that round in `pending_learning_rounds` for about three seconds, then `observed`, finishing at 0/16 lows with low-defense focus. Add `--duplicate-summaries` or `--drop-after-summary` to the first command for those cases. Restart the first command to replay; it resets the live folder. The brain's `/sessions/{id}/recording` still serves the full original file.

## Verification

```sh
python contracts/validate.py
python contracts/validate.py data/samples/practice_djin_vs_kaz.jsonl
python contracts/validate.py tools/mock/tests/fixtures/two-rounds.jsonl
python -m unittest discover -s tools/mock/tests
python tools/mock/tests/smoke.py
```

Expected: validators print `PASS`, unit tests pass, and the smoke script prints three `PASS` lines. The smoke test needs free local ports 8765–8767 and runs the actual launcher, HTTP APIs, WebSockets, occupied-port handling, and SIGINT shutdown. Its first two checks use temporary storage; its final check reads the repository's `data/` to verify discovery, both versus downloads and the neutral versus WebSocket. It stops its servers afterward. The small two-round test fixture is independent of the generator and covers frame resets, unknown fields/types, summaries and learning records.

When section 3.1 produces another recording, select its JSONL with `--recording`; provide its companion metadata and learning file in the documented locations. No server changes are needed.

## Synthetic session (section 3.1)

`python tools/mock/synth.py` writes a seeded three-round Devil Jin (human) vs Kazuya (bot) session to `DATA_DIR`: `recordings/`, `sessions/`, `learning/` and `profiles/`. It isn't committed (about 7 MB); the same seed gives the same file everywhere. The servers load it automatically from `DATA_DIR`, and it streams with `ws://localhost:8765/ws/state?session=2026-10-17T13-05-00_synth_djin_vs_kaz`.

| Round | What happens (real Kazuya move ids) | Learning line | Winner |
|---|---|---|---|
| 1 | df+1 blocked, then d+4 low hits 4 of 5; one throw lands, one is broken | accuracy 0.41, `low_defense` p 0.8, mastery 0.22 | bot |
| 2 | lows hit 3 of 5; a df+2 mid catches a duck | accuracy 0.58, mastery 0.55 | bot |
| 3 | every low blocked and punished; the plan switches to mids and throws | accuracy 0.71, `low_defense` fixed, `player_changed` | human |

Result `loss 1-2`; `/learning` gives `time_to_detect.low_defense = 1` and `time_to_mastery.low_defense = 3`. Flags: `--seed`, `--rounds` (1–3), `--round-seconds` (30 minimum), `--player`, `--out`. Tests: `tests/test_synth.py`.

## Remediation and portability

The launcher uses POSIX asyncio signal handlers where supported and a standard signal fallback on Windows; previous handlers are restored on exit or startup failure. Native Windows validation remains pending. Invalid discovered metadata is isolated to its session; explicitly selected invalid input fails startup with a diagnostic. Each service returns 503 when requested session data is invalid.

For a complete checked-in three-round session, use [the synthetic bundle](../../data/samples/synthetic/README.md). Set `DATA_DIR` to that bundle for both the mock and real analytics. Mock dependencies include the Sentry SDK for shared no-op spans; the mock never initializes telemetry or requires a DSN.
