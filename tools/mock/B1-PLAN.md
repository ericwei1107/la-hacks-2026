# B1: zipped versus recordings

## Goal

Serve Sahil's two checked-in versus archives through the mock session APIs and playback without extracting files or importing `game/`. Work stays within `tools/mock/`; contracts remain frozen.

## Implementation

1. Discover `.zip` alongside `.jsonl` in `DATA_DIR/samples/` and `DATA_DIR/recordings/`. Accept archives through repeatable `--recording` and existing metadata references.
2. Require exactly one recording `.jsonl` (excluding `.learning.jsonl`) and its same-directory, same-stem `.session.json` inside each archive. Read members directly, preserve the recording bytes, and run the existing tolerant JSONL parser and schema validation. Reject corrupt or ambiguous archives with a diagnostic; isolate invalid discovered archives as existing discovery does for JSONL.
3. Return the decompressed recording bytes from the recording endpoint with `application/x-ndjson`. Playback and replay analysis consume the same validated records as ordinary recordings.
4. Preserve selection: newest session by default; first `--recording` overrides it. Use external learning/eval files and inline learning as already supported.
5. Document discovery, archive layout, selection, and verification commands.

## Verification

- Regression tests cover nested archive members, ignored learning members, paired metadata, ambiguous/corrupt input, invalid schemas, truncated final records, discovery, selection, exact recording downloads, and both WebSocket channels.
- Verify the shipped versus archives list with practice and the locally generated synthetic session (four sessions on this workspace), and stream the neutral session by id. The synthetic session is optional local data, so a clean checkout can list three sessions.
- Run `.venv/bin/python -m unittest discover -s tools/mock/tests`, `.venv/bin/python contracts/validate.py`, and `.venv/bin/python tools/mock/tests/smoke.py`.

The prerequisite mock hardening and synthetic fixture are already present on the current `Eric` branch. This implementation needs no branch merge or publishing action.

## Result

Implemented and verified on October 17, 2026:

- Mock unit suite: 46 tests passed, including seven archive regression tests.
- Frozen contract examples: `PASS`.
- Live smoke test: all three checks passed; automatic discovery listed four sessions, including both versus recordings. Both decompressed downloads matched their original JSONL bytes, and the neutral versus session streamed over WebSocket. Servers shut down after the checks.
- `git diff --check`: passed.

Run `.venv/bin/python tools/mock/serve.py --services brain,replay` from the repository root. Expect four sessions with the current local data, newest/default `2026-10-18T01-24-57_sahil_djin_vs_kaz`, with brain on port 8765 and replay on port 8766.
