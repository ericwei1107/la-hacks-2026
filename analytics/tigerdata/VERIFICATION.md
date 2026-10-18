# Tiger Data verification — 2026-10-17

The updated schema was applied to the configured cloud service through `analytics/.env`; credentials were neither printed nor committed.

- Explicit `init` succeeded, including four hypertables and `session_trends` continuous aggregate.
- Backfill imported 4 completed rounds with no invalid sessions. Repeated backfill reported `imported=0 unchanged=4 invalid_sessions=0`.
- The opt-in live integration test passed without skipping. Its temporary schema verified repeated initialization, four hypertables, the aggregate, expected raw/calculated row counts, aggregate/file parity, database repository reads, outage fallback, corrected-round replacement, late learning, actual constraint-triggered rollback, and disconnect/reconnect recovery. The temporary schema was removed afterward.
- The actual analytics server ran with the configured Tiger Data connection on temporary port 18768. Health, stats and learning returned 200; trends matched file results. It shut down cleanly.
- Local analytics suite: 62 cases, 61 passed and the opt-in cloud case skipped in that run; the cloud case subsequently passed separately. Mock suite: 34 passed. Frozen contract examples and the real sample validated. Real analytics alongside mock brain/replay passed the temporary-data smoke test and shut down cleanly.

Reproduce the cloud test from a terminal with `DATABASE_URL` configured:

```sh
TIGERDATA_RUN_INTEGRATION=1 .venv/bin/python -m unittest discover -s analytics/tests -p test_tigerdata_integration.py -v
```

Expected: one live test passes with `OK`, without a skipped marker. The watcher and API are independent; stopping the watcher pauses uploads until the next backfill or watcher run. Local files remain required for the API's authoritative session catalogue and freshness checks.
