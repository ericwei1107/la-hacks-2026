# Generated insight review examples

These are full internal snapshots produced by `analytics/insight_examples.py` through `InsightRepository`, using a five-moment limit. They are review fixtures, not an approved public API or a data source for the released app. Source input construction lives in the generator; do not hand-edit the JSON. The real example derives solely from the already checked-in real recording. Every other example is explicitly synthetic.

| Example | Review this behavior |
| --- | --- |
| [real.json](real.json) | 0/16 low blocks, 1/4 throw breaks, 0/6 estimated punishes; low-defense focus; first-fixed round 2 followed by current after-block regression; null evaluation |
| [synthetic.json](synthetic.json) | Three planted rounds, synthetic badge, first/current habit history; no human-improvement claim |
| [observed.json](observed.json) | Six observed low failures qualify for automatic focus; report unavailable, event-only moments |
| [early_signal.json](early_signal.json) | Three opportunities show a fraction and early-signal wording; no automatic focus |
| [no_opportunities.json](no_opportunities.json) | Null rate and zero opportunities, unavailable percentage |
| [invalid_recording.json](invalid_recording.json) | A complete malformed line invalidates recommendations and derived rates |
| [orphan_break.json](orphan_break.json) | Overall source parses, but the throw metric is invalid (1 success, zero observed attempts); never show 100% or clamp it |
| [manual_focus.json](manual_focus.json) | Manual throw focus can use three observations; preserve the manual/early-signal labels |
| [pending_learning.json](pending_learning.json) | Recording has two completed rounds; learning has round 1, with round 2 pending |
| [current_learning.json](current_learning.json) | Same recording after learning catches up; source snapshot changes, counts remain unchanged |
| [mixed_outcomes.json](mixed_outcomes.json) | One low was blocked but its punish opportunity was missed; use the separate per-metric outcomes |

All action wording remains a draft awaiting Garrett. Chloe can review the card with neutral “Review these moments” text while mechanics are pending. Report unavailable is the normal event-only fallback; a report marked `available_unverified_revision` still does not prove it matches the current recording.

```sh
.venv/bin/python -m analytics.insight_examples --check
```

Expected: `PASS: 11 generated insight examples match the builder`. To intentionally regenerate after a reviewed implementation/source change, run the same module without `--check`, inspect the diffs, and rerun the drift/schema tests. Source revisions and policy/format versions determine snapshot identity; there is no wall-clock timestamp or machine path in these snapshots.

See [display rules](../../handoffs/insights-ui.md), [the interface proposal and TypeScript sketch](../../INSIGHTS_PROPOSAL.md), and [the remediation plan](../../handoffs/insights-host-plan.md). Owner acceptance and native UI observations remain separate from the automated fixture checks.
