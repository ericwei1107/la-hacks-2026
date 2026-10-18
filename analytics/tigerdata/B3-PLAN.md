# B3: refresh Tiger Data for calculation version 4

Completed on 2026-10-18 UTC (2026-10-17 PDT). All acceptance checks passed;
see [verification evidence](VERIFICATION.md#b3-calculation-version-4-refresh).
PR #8 subsequently merged on 2026-10-18 UTC; the database refresh was verified independently of that merge.

## Scope and prerequisites

Recompute the configured cloud database using the existing importer, then retain
evidence that stored rounds and aggregate-backed trends match local version 4
calculations. No schema, contract, or runtime code change is expected.

The implementation is present on `Eric` at `58ff04a`, including the version 4
plain-low calculation and versioned round/trend fingerprints. The refresh ran
while PR #8 was open, without merging the PR or changing shared team rules.
Credentials come privately from ignored `analytics/.env`.

## Implementation sequence

1. Discover local sessions and completed rounds; compare current cloud checkpoints
   with locally prepared version 4 fingerprints before making changes.
2. Save a private logical snapshot of existing `kumite` application tables and
   aggregate rows under ignored `data/tigerdata-backups/`. Preserve source files.
3. Run the existing `init`, then `backfill --data-dir ./data` twice. The first pass
   must rebuild stale rounds; the second must import zero rounds, with no invalid
   sessions on either pass.
4. Check every discovered round checkpoint and calculated row against version 4
   preparation. Check published aggregate signatures and metric values against
   the file reducer. Use the importer's existing discovery policy: completed real
   and synthetic sessions already discoverable from `./data` are included; do not
   extract ZIPs or add nested fixtures to the demo catalogue in B3.
5. Run the opt-in cloud integration test without skips. Run an actual temporary
   loopback analytics server with cloud credentials and compare HTTP `/trends`
   with file-only responses. Force the hybrid repository's file reducer to fail
   in a separate check to prove that the aggregate supplied the data.
6. Run the existing analytics regression suite and frozen contract validator.
   Update `VERIFICATION.md` and the stale version-3 README guidance with measured
   results, reproduction commands, snapshot location and remaining limitations.

## Acceptance criteria

- Private pre-refresh snapshot exists, with a recorded digest and row counts.
- Backfill reports no invalid sessions and its immediate repeat imports zero.
- All local completed-round fingerprints and calculated rows match the cloud.
- Aggregate values and HTTP trend responses equal file results for every local
  player/character pair; the Sahil/Devil Jin route is explicitly checked.
- The live integration test passes without skips; regression and contract checks
  pass. Verification distinguishes imported sessions from intentionally excluded
  ZIP-only and nested synthetic sample files.

## Recovery and process handling

The existing importer replaces each round transactionally and withholds aggregate
publication until refresh succeeds. On failure, stop and retain the snapshot;
files remain the API fallback. Do not reset cloud tables. Existing long-lived API
and watcher processes must be restarted by their owner to load version 4. Only
temporary verification processes started for this task are stopped here.
