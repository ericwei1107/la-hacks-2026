# Recording inspection milestone

Goal: inspect a real recording locally without claiming optimal moves or model scores.

Scope: only replay/ source, tests, and documentation. Existing contracts and
character files remain unchanged. Generated artifacts go under DATA_DIR/inspections/,
separate from the eventual contract report endpoint. Code files contain no comments.

- [x] Reader: stream JSONL with source line numbers, validate known schema types,
  ignore unknown record types, accept arbitrary tactical sources, tolerate only an
  incomplete final JSON line, reject malformed interior records and mixed sessions.
- [x] Inspection: preserve round/frame identity; use human_slot and player.slot;
  prefer explicit human decision-point situation/action labels; extract observed
  hits, blocks, whiffs, throws, breaks, and knockdowns with correctly attributed
  roles. Unknown human identity is a limitation, not a guessed slot.
- [x] Context and outcomes: snapshots must never look ahead or cross rounds;
  report health-loss observations over the next 60 frames, bounded by round end,
  with missing coverage, duplicate frames, and health recovery marked. Event damage
  and health-loss totals are separate and are not causal or avoidable-damage claims.
- [x] CLI: write JSON and readable Markdown, reject ZIP input with extraction
  instructions, use DATA_DIR, sanitize generated filenames, protect source files,
  and refuse accidental replacement unless --overwrite is explicitly provided.
- [x] Verify: meaningful synthetic edge-case tests plus the downloaded real sample;
  run the whole replay suite and the unchanged contract validator, generate and
  inspect the real report, and request a read-only review before completion.

Interfaces: read_recording(path) -> Recording; build_inspection(recording) -> dict;
write_inspection(report, output_dir, overwrite=False) -> (json_path, markdown_path).
python -m replay.inspect RECORDING [--output-dir PATH] [--overwrite] is the CLI.

Review focus: human slot 1 / reversed player order; frame resets; truncated final
lines; missing human/state/damage fields; bot tactical sources never becoming human
actions; incomplete and reset-contaminated outcome windows; unsafe session filenames.

Review: independent read-only review found truncated numeric/Unicode tokens could
reject a valid incomplete final write. Regression tests failed, then passed after
the fix. Additional tests pin explicit identity-change limitations and state-line
citations for health windows. No changes to characters/ or contracts/ were needed.
