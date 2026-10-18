# Tiger Data evidence draft

Kumite keeps files authoritative while using Tiger Data for time-series ingestion and aggregate-backed trends. The existing importer batches completed rounds, fingerprints source/calculation revisions, supports idempotent repeat imports and falls back to files when database results are unavailable or stale.

The approved real-learning intake retained four imported completed rounds, followed by zero imported/four unchanged on the immediate repeat. Stored totals were 10,080 frames, 238 events and twelve round metrics. All four calculated payloads/fingerprints and twenty-eight final aggregate values matched the file path. The aggregate-backed route was checked with file trend fallback disabled. These are dated results documented in `../LIVE_LEARNING_VERIFICATION.md` and `../tigerdata/VERIFICATION.md`.

The new insight export is file-backed and does not require another cloud write. Existing calculation version 4 is preserved. A future change to stored semantics needs its own version bump, approved scoped recomputation, parity proof and zero-import repeat.

Do not describe current online prediction accuracy as held-out improvement, the archive as a cloud backup, or this export run as a fresh database verification. Before submission, link the retained measured evidence and actual demo-host database/fallback observation.
