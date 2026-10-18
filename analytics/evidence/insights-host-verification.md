# Insights examples and demo-source verification

Verified October 18, 2026 on Eric's Mac with Python 3.12.1. Base `c87dcbe` plus the implementation tree on `track-d-insights-host-handoff`. The internal builder/schema match the previously verified SHA-256 hashes; concurrent experimental API files are excluded from this branch. This is local implementation/HTTP evidence, not a Windows/game/app run.

| Check | Result |
| --- | --- |
| Chloe branch context | Refreshed `origin/chloe=6e66871`, `origin/chloe-eric=914fc5e`; both are included on Eric; C2 subsequently reached main in PR #21 at merge `f702d13`, with the same head |
| Generated examples | Eleven full internal snapshots from the production builder; schema/state checks and exact regeneration drift test pass |
| TypeScript sketch | Extracted from the proposal; TypeScript strict/no-emit check passed |
| Full analytics suite | 152 cases: 151 passed, one opt-in cloud skip |
| Full mock suite | 46/46 passed |
| Frozen contracts | `contracts/validate.py` passed; no contract files changed |
| Existing synthetic and real smokes | Both passed HTTP/WebSocket assertions and clean shutdown |
| New host source/CLI smoke | Actual brain API plus actual analytics launcher/check CLI, temporary ports and canonical copy of the real fixture: passed |
| Native host, live app and owner review | Pending; no actual host path/address supplied and no native run claimed |

## Demo-host answers and follow-up (October 18, after PR #22 opened)

Sahil confirmed the layout: brain, replay and analytics share `C:\Users\sahil\la-hacks-2026\data` on his laptop, with no remote execution before the demo. He will run the source check against a live session and paste the output, and accepted PR #22 limited to `analytics/` and `tools/`. Follow-up verified on Eric's Mac in the PR worktree:

| Check | Result |
| --- | --- |
| Recorder-relative metadata | Recorder writes `DATA_DIR/recordings/<id>.jsonl`, relative when `DATA_DIR` is the default `data`. Such references now resolve to that canonical file when absent under the code checkout, so the check runs from a detached worktree. A unit test fails without the fix and passes with it |
| Check during continuous writes | Mid-round growth no longer fails as "changing": prefix bytes must be unchanged and closed stats rounds plus closed, saved learning rounds must match. Static sources keep exact equality. Rewritten earlier bytes still fail |
| One-command before/after | `--session-id latest --wait-for-round-seconds N` captures a passing check before and after a later completed round with saved learning (exit 0), or exits 2 on timeout |
| Main vs branch reducers | `origin/main` analytics and this branch return byte-identical `/stats` and `/learning` bodies for the real and synthetic samples |
| Full analytics suite | 161 cases: 160 passed, one opt-in cloud skip |
| Mock suite, contracts, examples | 46/46; frozen examples pass; eleven examples match |
| Smokes | `smoke.py`, `live_learning_smoke.py` and the extended `demo_host_smoke.py` (relative metadata, before/after CLI, continuous writer) pass with clean shutdown |
| Native host | Pending Sahil's pasted output; nothing has been run on the laptop by Track D |

## `/insights` stall during live play: fixed (October 18)

Chloe reported `/insights` stalling or timing out from about 20 to 45 seconds in the mock live scenario at `--rate 240`, so the focus card skipped round 3. Reproduced and fixed on Eric's Mac (local measurements, not native-host evidence). Method: the mock live scenario with real analytics and `KUMITE_EXPERIMENTAL_INSIGHTS=1` on a temporary folder; `/insights`, `/stats` and `/learning` requested concurrently once a second, as the app does.

**Cause.** A cache miss cost about 2.7 s, 95% of it JSON-schema validation of all 10,336 recording lines. During live play the recording changes every flush, so every request missed the cache, and requests queued behind the repository lock.

**Fix.** `InsightRepository` now keeps the parsed result of the recording prefix it has already read and validates only newly appended complete lines, mirroring `TailReader` for `/stats`. A rewritten, truncated or replaced file triggers a full reparse. Snapshots are identical to a fresh full parse (new regression tests), and an append validates only the new lines.

| Run | `/insights` OK | Timeouts | p50 / p95 / max | Rounds observed |
| --- | --- | --- | --- | --- |
| Before, `--rate 240` | 28/50 | 22 (19–40 s) | 872 / 4080 / 4966 ms | 1, 2, 4 |
| After, `--rate 240` | 50/50 | 0 | 183 / 266 / 459 ms | 1, 2, 3, 4 |
| After, real speed (60 fps, full session) | 174/174 | 0 | 94 / 235 / 608 ms | 1, 2, 3, 4 |

After the fix `/insights` matches `/stats` under identical load (at 4x speed: 259 ms p95; at real speed: 232 ms p95), so the remaining latency is shared machine contention, not the route. Each round shows pending learning for about 3 seconds, then observed, ending at 0/16 lows with low-defense focus.

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
