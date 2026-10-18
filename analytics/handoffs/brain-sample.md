# B4: Sahil's real summaries and learning sample

Sahil supplied the real M3 sample on main in `23eb63e`: `data/samples/live_learning/`, session `2026-10-18T05-14-03_sahil_djin_vs_kaz`. The local intake is verified; see [retained B4 results](../LIVE_LEARNING_VERIFICATION.md) for counts, regression tests and HTTP/WebSocket checks. The low habit is detected/exploited but never fixed; the fixed/regressed transition belongs to `after_block:any`. The owner subsequently approved cloud upload: all four rounds are imported, repeat backfill is unchanged, and aggregate-backed API responses match files. Deliberate re-test reporting remains unverified.

## Files to provide

Use one consistent `<session_id>` and the existing frozen contracts:

- `recordings/<session_id>.jsonl`: real state/events and the producer's round summaries.
- `sessions/<session_id>.json`: paired metadata with human slot, characters and actual mode.
- `learning/<session_id>.jsonl`: complete `learning_round` records for the same session and rounds.
- `eval/<session_id>.json`: optional, only when a real held-out eval has been run; otherwise fine-tune values stay null.

For checked-in review material, bundle these directories under `data/samples/<bundle>/` and use that directory as `DATA_DIR`, as with the synthetic bundle. Generated live data stays outside Git. No contract changes are needed. Keep game timing in the round frame counter and retain slot identity rather than interpreting screen side as human/bot.

## Intake checks after the ship

Validate the recording and metadata against their schemas and every learning record against the metrics round definition. Confirm ids/rounds match and summaries agree with the producer's learning output. Run the analytics and mock suites, then compare `/stats`, `/learning` and `/trends` with the supplied real data. Verify nonempty learning rounds, detection/mastery transitions and null eval values when no eval exists.

Do not derive deliberate re-test results without explicit producer evidence. Report decision counts and observed frequencies separately from model probability estimates and mastery. Cloud backfill follows file verification; a newly received sample alone does not prove imported aggregate parity.

Sentry remains a separate follow-up after brain API/M4: [5% sampling and retained timing/trace evidence](sentry-brain.md).
