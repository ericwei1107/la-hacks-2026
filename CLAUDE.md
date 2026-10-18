# Kumite repo instructions for agents

Kumite is an offline Tekken 8 sparring bot built by four people in 24 hours. Only Sahil's laptop has the game; everyone else builds against `contracts/` and `tools/mock/`.

## Who owns what
- `game/` Sahil (Track A): reader, hot loop, reflex, tactical (Laya), learning system, recorder, brain API on :8765.
- `app/` Chloe (Track B): Electron + React + Vite desktop app, overlay window, ElevenLabs voice.
- `replay/` and `characters/` Garrett (Track C): replay analysis + coach service on :8766, Jev scoring.
- `analytics/` and `tools/mock/` Eric (Track D): analytics service on :8767, mocks, Tiger Data, Sentry. The Laya/Veri fine-tune is `game/` (Sahil).

Only edit the folders your owner owns. Cross-track needs go through `contracts/`.

## Rules
- Read `contracts/api.md` and `contracts/recording.md` before writing any code that produces or consumes data. Validate outputs against `contracts/*.schema.json`; run `python contracts/validate.py` after any contract-facing change.
- Contracts are frozen. Do not edit `contracts/` unless your owner says all four agreed.
- If `prep/design-doc.md` exists locally, it is the full design; read Section 16 and your track's brief in Section 18 first. `prep/` is never committed.
- Never commit anything under `data/` except `data/samples/`, and never commit keys or `.env` files.
- Code files contain no comments. Explanations go in commit messages and task summaries.
- Every service reads `DATA_DIR` and exposes `GET /health`.
- `game/` only: read-only `ReadProcessMemory` on `Polaris-Win64-Shipping.exe`. Never write game memory, never inject, never attach a debugger. Offline modes only.
- End every task with the exact command to run and what the owner should see.
