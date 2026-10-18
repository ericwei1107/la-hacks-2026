# Observed defense metrics

The shared `stats.opportunities` calculation supplies `/stats` and the internal evidence export. Calculation version 6 identifies the corrected punish calculation and versioned Tiger Data fingerprints. Internal metric definitions are version 2; insight format and focus rule versions remain 1. No new fields are added to frozen APIs. See [verified rollout](evidence/punish-rollout.md).

| Metric | Successes | Opportunities | Limits |
| --- | --- | --- | --- |
| Low defense | Human blocks of bot plain-low contacts | Bot plain-low blocks, hits and counter-hits targeting the human | Special lows excluded; contacts are not every low selected or attempted |
| Throw defense | Human throw-break events | Bot throw events targeting the human, including escaped throws | A break does not add an attempt; excess/unpaired breaks invalidate the new explained rate |
| Estimated punish conversion | Verified human hits paired with unsafe blocked bot moves | Bot blocks at actor-relative advantage ≤ −10, with consistent recovery timing and state evidence, excluding continuations | Hits land after human recovery and at or before bot recovery, with no tolerance. Unknown/ambiguous timing makes the rate unavailable; it is still estimated |

Punish matching processes human hits in round/frame order and assigns each hit to the most recent unmatched qualifying opportunity in the same round. One hit satisfies one opportunity; a second hit can satisfy another. Same-frame source records remain distinct. Side switches do not change human block-slot identity. The legacy capped throw rate remains unchanged, but the new export exposes impossible raw counts instead of hiding them.

Throw-break association is a diagnostic pairing with the latest preceding unmatched bot throw in the same round. No new throw timing window or throw identity is inferred. An unpaired break is an anomaly, not evidence that the player failed or succeeded in an invented attempt.

## Populations, states and evidence

New focus/export counters use rounds explicitly closed by `round_end` or `round_summary`. Existing `/stats` may include an active round, so its live total can be newer than the completed-round export. No closure is inferred from increasing frames or a winner in a mutable profile.

- `no_opportunities`: denominator zero, value null.
- `early_signal`: one to four valid opportunities; a measured fraction is available, but automatic focus is ineligible.
- `observed`: at least five valid opportunities. This is a product eligibility rule, not statistical significance.
- `invalid`: skipped recording lines, uncertain punish timing or impossible/unpaired counts. Raw successes/opportunities remain visible; value is null and automatic focus is suppressed.

Every opportunity retains its original physical JSONL line, round/frame, session and consumed recording-prefix SHA-256. Blank lines and unsupported records still occupy original line positions. Matched responses have their own references. Metrics return at most three sample references and `evidence_total`; complete counts never come from the limited list. The internal `analyze` function retains every contributing reference for audits.

The real acceptance bundle independently yields **0/16 lows, 1/4 throws and 1/5 estimated punishes**. Its sixteen lows comprise twelve hits and four counter-hits. The producer's final low habit has fifteen observations; it measures a different population.

## Interpretation

Producer first-fixed round is historical and survives later regression; current status comes from the latest completed-round producer record. Unknown extensions do not establish deliberate retests. Online prediction accuracy is bot behavior, without reconstructed correct/total counts. Bandit estimates are not observed hit rates. Fine-tune before/after stays null without a valid evaluation artifact.

Automatic focus ranks failures, then failure fraction, then low defense / throw defense / punishment. It requires at least five opportunities and one failure. A manual internal override may select an early signal but cannot select invalid/no-opportunity metrics. Punishment focus is disabled until mechanical/advice review. Low/throw action wording is reviewed; it is not automatically sent to the game or app.

## Verify

```sh
SENTRY_DSN= DATABASE_URL= .venv/bin/python -m unittest discover -s analytics/tests -p test_insights.py -v
```

Expect metric/provenance, snapshot, focus and real-fixture tests to pass. Existing API/Tiger Data suites verify the nullable response contract and versioned freshness.

Unknown recovery evidence invalidates the punish value rather than counting a miss. The legacy synthetic bundle has no recovery details and therefore no usable punish rate.
