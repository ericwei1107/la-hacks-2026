# Observed defense metrics

The shared `stats.opportunities` calculation supplies both existing version-4 rates and the new internal evidence export. Existing HTTP responses and Tiger Data payloads keep calculation version 4. Insight format, metric definitions and focus rules have separate version 1 identifiers. No new counts are added to frozen APIs.

| Metric | Successes | Opportunities | Limits |
| --- | --- | --- | --- |
| Low defense | Human blocks of bot plain-low contacts | Bot plain-low blocks, hits and counter-hits targeting the human | Special lows excluded; contacts are not every low selected or attempted |
| Throw defense | Human throw-break events | Bot throw events targeting the human, including escaped throws | A break does not add an attempt; excess/unpaired breaks invalidate the new explained rate |
| Estimated punish conversion | Qualifying human hits paired with unsafe blocked bot moves | Bot block events targeting the human at actor-relative advantage ≤ −10 | Window is `abs(advantage) + 10` round frames from the block event; this is an estimate, not a guaranteed mechanical punish. The [real-session audit](evidence/punish-audit.md) found the window ignores blockstun (a landed punish scored as a miss) and counts mid-string blocks; Garrett reviewed it and accepts the corrected rule conditionally; it stays unimplemented until a corrected reducer, regressions, calculation-version bump and backfill are verified |

Punish matching processes human hits in round/frame order and assigns each hit to the most recent unmatched qualifying opportunity in the same round. One hit satisfies one opportunity; a second hit can satisfy another. Same-frame source records remain distinct. Side switches do not change human block-slot identity. The legacy capped throw rate remains unchanged, but the new export exposes impossible raw counts instead of hiding them.

Throw-break association is a diagnostic pairing with the latest preceding unmatched bot throw in the same round. No new throw timing window or throw identity is inferred. An unpaired break is an anomaly, not evidence that the player failed or succeeded in an invented attempt.

## Populations, states and evidence

New focus/export counters use rounds explicitly closed by `round_end` or `round_summary`. Existing `/stats` may include an active round, so its live total can be newer than the completed-round export. No closure is inferred from increasing frames or a winner in a mutable profile.

- `no_opportunities`: denominator zero, value null.
- `early_signal`: one to four valid opportunities; a measured fraction is available, but automatic focus is ineligible.
- `observed`: at least five valid opportunities. This is a product eligibility rule, not statistical significance.
- `invalid`: skipped recording lines or impossible/unpaired counts. Raw successes/opportunities remain visible; value is null and automatic focus is suppressed.

Every opportunity retains its original physical JSONL line, round/frame, session and consumed recording-prefix SHA-256. Blank lines and unsupported records still occupy original line positions. Matched responses have their own references. Metrics return at most three sample references and `evidence_total`; complete counts never come from the limited list. The internal `analyze` function retains every contributing reference for audits.

The real acceptance bundle independently yields **0/16 lows, 1/4 throws and 0/6 estimated punishes**. Its sixteen lows comprise twelve hits and four counter-hits. The producer's final low habit has fifteen observations; it measures a different population.

## Interpretation

Producer first-fixed round is historical and survives later regression; current status comes from the latest completed-round producer record. Unknown extensions do not establish deliberate retests. Online prediction accuracy is bot behavior, without reconstructed correct/total counts. Bandit estimates are not observed hit rates. Fine-tune before/after stays null without a valid evaluation artifact.

Automatic focus ranks failures, then failure fraction, then low defense / throw defense / punishment. It requires at least five opportunities and one failure. A manual internal override may select an early signal but cannot select invalid/no-opportunity metrics. Punishment focus is disabled until mechanical/advice review. All action text is labelled draft pending Garrett review; it is not automatically sent to the game or app.

## Verify

```sh
SENTRY_DSN= DATABASE_URL= .venv/bin/python -m unittest discover -s analytics/tests -p test_insights.py -v
```

Expect metric/provenance, snapshot, focus and real-fixture tests to pass. Existing legacy/API/Tiger Data suites separately protect version-4 compatibility.
