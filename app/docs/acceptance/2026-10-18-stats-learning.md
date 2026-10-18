# Acceptance: Stats and Learning correctness (Track D plan, C2)

Checked on 2026-10-18 against real analytics and mock brain/replay serving the real live-learning set.

## Setup

- Analytics at commit `914fc5e` (Eric's `dc1f90c` plus the C1 checker): `DATA_DIR=./data/samples/live_learning DATABASE_URL= SENTRY_DSN= .venv/bin/python -m uvicorn analytics.main:app --port 8777`
- Mock brain and replay with the same `DATA_DIR`, on ports 8785 and 8786.
- The built app: `KUMITE_BRAIN_URL=http://127.0.0.1:8785 KUMITE_REPLAY_URL=http://127.0.0.1:8786 KUMITE_ANALYTICS_URL=http://127.0.0.1:8777 KUMITE_OVERLAY=0 npx electron .`
- Session `2026-10-18T05-14-03_sahil_djin_vs_kaz`. `npm run typecheck` and `npm run build` pass.

## Observed

| Item | Expected | Seen |
|---|---|---|
| Throws broken, Sessions totals | 1 of 4 (four bot throws at the human, one broken) | "1 of 4" |
| Throw break rate, Stats | 25%, agreeing with `/stats` | "25%" with "1 of 4 broken" |
| Null rates | Shown as unavailable | The sample's totals have no nulls; a null total shows "—" and "Didn't come up this set" (MAIN-STATS-008, read in code) |
| Fine-tune | Not shown while `before` and `after` are null | Not shown; the screen never shows it |
| after_block:any | First fixed in round 2, not fixed in round 4 | Green belt, "Fixed in round 2, slipped since.", to-master 2 muted; "No black belt yet" |
| low_defense | Never fixed | Yellow belt, the bot's target, to-master "—" |
| Hero at 100% | Fits its column | 100% at 120 px, clear of the chart frame |

## Not exercised here

- The "Round <n> is still being saved." note and the 2-second catch-up: the mock's recording is static, so its stats and learning already hold every round when a summary arrives. Needs a growing session on the demo host.
- Refetch on a new live set and when the round stops being live: needs the live brain.
- Three habits read "After you block" (`after_block:any`, `after_block:bot_minus`, `after_block:bot_plus`). The habit words do not tell these situations apart; a naming follow-up for the design system.
