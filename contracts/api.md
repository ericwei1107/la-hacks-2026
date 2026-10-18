# Service APIs

Three services, all JSON over HTTP. Bodies validate against the schemas in this folder. Every service has `GET /health` → `{"ok": true, "service": "<name>", "version": "<git sha>"}` and reads `DATA_DIR`. CORS is open to the desktop app.

| Service | Owner | Port | Address variable |
|---|---|---|---|
| Brain | Sahil (Track A) | 8765 | `KUMITE_BRAIN_URL` |
| Replay analysis | Garrett (Track C) | 8766 | `KUMITE_REPLAY_URL` |
| Analytics | Eric (Track D) | 8767 | `KUMITE_ANALYTICS_URL` |

`tools/mock/` serves all three from a recording file, on the same ports, so every client can be built before the real services exist.

## Brain :8765

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/sessions` | — | `[session.schema.json]`, newest first |
| GET | `/sessions/{id}` | — | `session.schema.json` |
| GET | `/sessions/{id}/recording` | — | the JSONL file, `application/x-ndjson` |
| GET | `/profiles/{player}` | — | `[profile.schema.json]` (one per character) |
| GET | `/config` | — | `config.schema.json` |
| POST | `/config` | `config.schema.json` (partial allowed) | `config.schema.json` (the merged result) |
| WS | `/ws/state` | — | stream of `gamestate` and `event` records, as JSON text frames, at up to 60 per second |
| WS | `/ws/coach` | — | stream of `{"t": "coach", "session_id", "round", "text", "severity"}` and `round_summary` records |

`/ws/state` may drop frames under load; clients must not assume every frame arrives. Events are never dropped.

## Replay analysis :8766

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/coach/round` | `round_summary.schema.json` | `{"text": string, "severity": "info" \| "warn" \| "praise"}`; must answer in under 8 s; `text` under 40 words |
| POST | `/analyze/{session_id}` | — | `report.schema.json`; also written to `data/reports/` |
| GET | `/reports/{session_id}` | — | `report.schema.json`, 404 if not analyzed |
| POST | `/coach/chat` | `{"session_id": string, "player": string, "message": string, "history": [{"role", "text"}]}` | `{"text": string, "citations": [{"frame": int, "round": int}]}` |

## Analytics :8767

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/stats/{session_id}` | — | `{"session_id", "rounds": [{"round", "damage_taken_by_situation": {situation: int}, "punish_rate", "throw_break_rate", "low_block_rate", "counter_hits_taken", "counter_hits_given", "avg_adv_after_block"}], "totals": {same keys}}` |
| GET | `/trends/{player}/{character}` | `?stat=<name>` optional | `{"player", "character", "series": [{"session_id", "started_at", "values": {stat: number}}]}` |
| GET | `/learning/{session_id}` | — | `metrics.schema.json` |
| GET | `/insights/{session_id}` | `?limit=1..50` optional, default 5 moments | `insights.schema.json`; 404 unknown session, 422 bad id or limit, 503 sources unavailable or changing |

Rates are 0–1 or `null` when the situation never occurred.

## Changing a contract

Contracts are frozen. A change needs Sahil, Chloe, Garrett and Eric to agree in the team chat, then one commit that updates the schema, its example, and `api.md` together, with `python contracts/validate.py` passing.
