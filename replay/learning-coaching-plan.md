# Learning and move-specific coaching follow-up

Read mastery from DATA_DIR/learning/<session_id>.jsonl using the frozen metrics round schema. Use the latest valid same-session round no later than the analyzed recording. Preserve the exact mastery estimate with path/round/line evidence; omit it with a limitation if unavailable. Do not carry an absent latest value forward or infer improvement.

Resolve the bot move from a matching biggest moment or after_block suffix using Claude's read-only character lookup. Require a unique result, retain conservative timing/range restrictions, and use verified matchup guidance for short grounded templates. Unknown identities, shared IDs, sparse evidence and absent files retain generic tips. Existing provider selection can choose only prepared tips, preventing invented move names. Improve spoken fixed-habit wording.

Add tests first for latest snapshots, missing/malformed/mismatched files, stale/future rounds, non-finite estimates, known/unknown/ambiguous moves, compact after_block labels, timeout fallback, and praise wording. Verify the full replay suite, contracts, and a DATA_DIR-layout synthetic recording offline. Confirm the real live_learning sample separately when it exists. Do not edit Claude's three designated files, characters or contracts.
