# Punish correction: verified version-6 rollout

Completed October 18, 2026, in the approved 15-minute maintenance window.
Scope: `2026-10-18T05-14-03_sahil_djin_vs_kaz`, rounds 1–4 only, existing `kumite`
schema. Sahil confirmed all services/watchers stopped and held them for this run.

## Result

The corrected session result is **1/5 estimated punishes (20%)**, replacing 0/6.
Low blocks remain 0/16 and throw breaks 1/4. Punish focus remains disabled.

| Acceptance | Verified result |
| --- | --- |
| First scoped backfill | 4 imported / 0 unchanged / 0 invalid |
| Immediate repeat | 0 imported / 4 unchanged / 0 invalid |
| Round checkpoints | All four match local version-6 preparation |
| Calculated round rows | Exact payload parity; rates `[0.5, 0.0, null, null]` |
| Aggregate | All 28 final metric values and source signature match files |
| Real loopback HTTP | Health, stats, learning and full/filtered trends return 200 |
| Aggregate route proof | File trend fallback disabled; `/stats` and `/trends` show 0.2 |
| Raw data | 10,080 frames and 238 events unchanged |
| Other sessions | All unrelated application-row counts/hashes unchanged |
| Sources | Recording, metadata and learning SHA-256 unchanged |
| Process cleanup | Temporary verification API stopped; no watcher started |

The [machine-readable receipt](punish-v6-cloud.json) records the production checks.
The import and all verification succeeded, so backup restoration was not needed.
No schema reset or initialization ran. Publication was locked across the scoped
import. If a partial import had failed, the prepared recovery would restore the
seven scoped application relations from the backup and refresh the aggregate,
then require all original row hashes to match. No restore is claimed as executed.

## Calculation identity and mechanics

Version **6** distinguishes this state-verified implementation from a different
local version-5 implementation. Reusing version 5 would let different algorithms
share round/source fingerprints. V4/v5 signatures are rejected by the v6 API.

Recovery is `detail.read_frame + total - frame`, with consistent human/bot gap
and recorded state coverage. Continuations are excluded. A human hit must land
after human recovery and at or before bot recovery, with no tolerance. Exact
boundary, continuation, uncertainty, both slots and one-to-one matching cases are
tested. Missing/ambiguous timing makes the punish rate unavailable, with source
references. Legacy synthetic recordings lack this recovery evidence and no longer
claim planted 9/9 punishes.

## App and verification

The null punish note is “Not enough data this set”. Design and MAIN-STATS-008
match the code. Eric explicitly approved the bounded exception to the unavailable
linked-intent-dev skill and sequential inspection. App typecheck/build passed;
no native Windows UI observation is claimed.

- Full analytics run: 186 tests, 185 passed, one opt-in cloud skip.
- Focused reducer/rollout regressions: 15 passed, including stale v4/v5 signatures.
- Mocks: 54 passed. Frozen contract examples: pass.
- Eleven internal and eleven public example fixtures match the builder.
- Live Tiger Data integration: one passed without skips; its uniquely named
  `kumite_test_*` schema was cleaned up. Rollback/reconnect checks passed there.
- App production build, including typecheck, passed again in the release window.
- `git diff --check`: pass. Frozen contracts and sample sources were not changed.

## Private recovery material

The scoped backup was taken in a repeatable-read, server-enforced read-only
transaction, decompressed and checked for scoped IDs, row counts, digest and
0600 permissions. It includes one session, four checkpoints, 10,080 frames,
238 events, 12 round metrics, 102 snapshots, one publication and 28 aggregate rows.
Compressed size: 695,905 bytes. SHA-256:
`e82b8c1d40bd920fc59f8f68453fd62cc3dc8344566a2d085579be3db2570e2b`.
Private path and operational receipts remain ignored under `data/`; backup data
and credentials are not committed. This is a scoped logical row backup requiring
the existing schema, not a full PostgreSQL dump. Unrelated raw data was not copied.

## Demo host activation

From Sahil's source-check worktree, fetch and check out the published rollout
commit, then confirm the imported module before starting analytics:

```powershell
git fetch origin fix/punish-v6-rollout
git switch --detach FETCH_HEAD
python -c "import analytics.stats as s; print(s.__file__); print(s.CALCULATION_VERSION); assert s.CALCULATION_VERSION == 6"
python -m analytics.demo_host serve --data-dir "C:\Users\sahil\la-hacks-2026\data" --host 127.0.0.1 --port 8767 --file-only
```

Expect the module path to be in the source-check worktree and version `6`.
The launcher prints the absolute shared DATA_DIR. Keep the agreed file-only demo
mode; the production cloud correction is independently verified. New live rounds
use their actual evidence and do not necessarily reproduce the historical 20%.
Only the audited sample is approved for cloud writes. Leave unscoped cloud
watchers off; restarting an old-version watcher could overwrite the correction.
Brain/replay/app can restart after the completion handoff. Source/flush/reconnect
and native UI acceptance still belong to Sahil/Chloe's live rehearsal.
