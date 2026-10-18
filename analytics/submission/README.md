# Track D submission evidence package

These are review drafts, not published submissions. Use the deterministic insight export for numerical claims. Track D's original B4 intake is complete; complete B5 and demo-host acceptance only when the owner artifacts have been independently checked.

## Reproduce the package

```sh
.venv/bin/python -m analytics.insights 2026-10-18T05-14-03_sahil_djin_vs_kaz --data-dir ./data/samples/live_learning --output-dir ./data/analytics
```

Keep generated JSON/Markdown local. Each contains the snapshot ID, source-prefix hashes, count definitions, historical/current habit observations, nullable evaluation and source-linked moments. This is the B7 export path; no separate calculation pipeline is used for video/write-ups.

## Claim ledger

| Draft claim | Evidence | Boundary |
| --- | --- | --- |
| Low defense was detected and exploited | Real export: 0/16 blocks, first detection round 3; 33 habit-driven decisions | Does not establish improved human low defense |
| Online prediction accuracy rose across the set | Four producer learning records: .6, .7333, .9048, 1 | Bot online metric; counts/baseline unavailable, not held-out eval |
| A habit was first fixed and later regressed | `after_block:any` first fixed round 2, regression round 3, latest fixed false | Low defense was never fixed; regression does not prove deliberate retests |
| Real recorded defense counts | New export: 1/4 breaks and 0/6 estimated punishes | Punish conversion retains provisional timing, not guaranteed punishability |
| Real sample reached Tiger Data with parity | `LIVE_LEARNING_VERIFICATION.md` and `tigerdata/VERIFICATION.md` | Dated earlier approved run, not rerun by the export |
| Replay model monitoring is retained | Successful trace linked in `SENTRY_VERIFICATION.md`, owner PRs #15/#16 | Temporary nano override, development environment, historical release |
| Local fallback preserves a coaching path | Owner replay evidence plus Eric/Chloe decision | Does not establish native spoken timing; Chloe's rehearsal pending |
| Internal insights work without model/database | Export tests with invalid DSN/DB values and no SDK initialization | New shared route and app consumer are not approved/delivered |
| Cached internal snapshots are fast locally | Twenty final local Mac captures: p50 14.925 ms, p95 15.502 ms, max 17.335 ms; ignored benchmark receipt retains code/source hashes | Not HTTP, Windows or full gameplay performance |
| Full brain decision monitoring | Trace `c5e0b584` verified, waterfall retained, owner on/off timings and acceptance in `evidence/brain-decision-2026-10-18.md` | Per-service traces only; no cross-service propagation claim; transport-unavailable behavior unreported |
| Held-out Laya fine-tune improvement | Owner-reported (Oct 18, code `561bcb0`): held-out session `2026-10-18T07-30-06_sahil_djin_vs_kaz`, balanced accuracy 45.0% base → 50.0% fine-tuned vs 40.0% majority baseline; plain accuracy 83.9% → 87.5% vs 80.4%. Eval file format verified compatible with `/learning` | Track D has not seen the file itself (it is on the demo laptop); one held-out session, model prediction accuracy, not human improvement |
| Human learning or retention | Unavailable | Do not claim from current recording |

Before publication, retain the exact export snapshot/command, current implementation commit and actual verification results. Check all numerical text against the generated artifact; screenshots must refer to the same session/source. Do not include secrets, raw environment dumps or a screenshot of another service as brain evidence.

Review draft `devpost.md`, `sentry.md` and `tigerdata.md` with the relevant owners. Chloe's C1/C2 are merged with passing local checks and a retained static app review; the checker reset follow-up and growing-session/native acceptance remain open. Insight contract approval and requested Luna migration are separate gates. No native timing, model migration or human-improvement outcome is implied by these drafts.
