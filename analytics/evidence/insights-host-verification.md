# Insights examples and demo-source verification

Verified October 18, 2026 on Eric's Mac with Python 3.12.1. Base `c87dcbe` plus the implementation tree on `track-d-insights-host-handoff`. The internal builder/schema match the previously verified SHA-256 hashes; concurrent experimental API files are excluded from this branch. This is local implementation/HTTP evidence, not a Windows/game/app run.

| Check | Result |
| --- | --- |
| Chloe branch context | Refreshed `origin/chloe=6e66871`, `origin/chloe-eric=914fc5e`; both are already included on Eric and have no newer commits |
| Generated examples | Eleven full internal snapshots from the production builder; schema/state checks and exact regeneration drift test pass |
| TypeScript sketch | Extracted from the proposal; TypeScript strict/no-emit check passed |
| Full analytics suite | 152 cases: 151 passed, one opt-in cloud skip |
| Full mock suite | 46/46 passed |
| Frozen contracts | `contracts/validate.py` passed; no contract files changed |
| Existing synthetic and real smokes | Both passed HTTP/WebSocket assertions and clean shutdown |
| New host source/CLI smoke | Actual brain API plus actual analytics launcher/check CLI, temporary ports and canonical copy of the real fixture: passed |
| Native host, live app and owner review | Pending; no actual host path/address supplied and no native run claimed |

## Source/HTTP rehearsal

The new smoke starts `game.api` and `analytics.demo_host serve` with the same temporary absolute DATA_DIR, with database, telemetry and external keys disabled. It calls the exact `analytics.demo_host check` CLI and verifies four completed real-fixture rounds, matching recording-prefix hashes and stats/learning parity.

It then appends explicitly scripted test data: an incomplete round-five event, the rest of that event plus a round end, and finally the companion learning record. The partial tail leaves the readable prefix at round four; a completed fifth recording round returns pending learning (exit 2); the later learning flush converges (exit 0 and a new snapshot). A second folder with the same session identity and a same-size recording edit is rejected (exit 1). The original checked-in bundle's complete file-hash manifest is unchanged, and all temporary child processes exit cleanly.

The scripted fifth round is synthetic test activity added only to the temporary copy. It supplies no new human-learning or native-host evidence. C1's separately reproduced reset false positive remains an owner follow-up; final native acceptance requires source snapshots before/after a real common completed round as well as the watcher and visual observations.

## Reproduce

```sh
.venv/bin/python -m analytics.insight_examples --check
SENTRY_DSN= DATABASE_URL= .venv/bin/python -m unittest discover -s analytics/tests -v
SENTRY_DSN= DATABASE_URL= .venv/bin/python -m unittest discover -s tools/mock/tests -v
.venv/bin/python contracts/validate.py
SENTRY_DSN= DATABASE_URL= .venv/bin/python analytics/tests/smoke.py
SENTRY_DSN= DATABASE_URL= .venv/bin/python analytics/tests/live_learning_smoke.py
SENTRY_DSN= DATABASE_URL= .venv/bin/python analytics/tests/demo_host_smoke.py
```

Expect eleven matching fixtures, the suite totals above, contract PASS and two PASS lines from each smoke. HTTP smokes need local loopback access. Use [INTEGRATION.md](../INTEGRATION.md) for the actual Windows launch/source-proof commands and pending owner observations.
