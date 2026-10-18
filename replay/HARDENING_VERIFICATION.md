# Replay correctness verification

October 18, 2026. Addresses all eight conditions found in the Track C readiness
review, plus two related cases found during independent review. No character,
Claude-designated lookup/options, app, analytics, tools or contract files changed.
No dependencies were added.

## Behavior verified

- Round advice requires a known disadvantage before recommending guarding.
  Bot-minus, pooled and unknown after-block situations get uncertainty-only
  fallback text; verified bot-plus/positive-on-block move guidance remains.
- Raw NaN and either Infinity are rejected with 422 before coaching, including
  nested extension fields. Tips remain at most 20 words and retain the existing
  one-second provider budget.
- Conflicting same-coordinate states are not scored or counted as human habits.
  Original events remain visible as unattributed evidence. Identical duplicates
  retain attribution, including when a later row would otherwise create doubt.
- Per-session analysis covers capture through scoring and publication under one
  lock. Queued analyses capture after earlier work finishes; different sessions
  remain concurrent. Cancellation does not release a transaction while its
  background save could still run; lock bookkeeping is cleaned up.
- A report decision's evidence_fingerprint binds original event evidence,
  context, scorer fields and full candidate descriptions. Chat refuses saved
  scores with changed state/event/menu or missing legacy fingerprints, retaining
  the existing move/menu/probability validation and limitations. Reanalyze a
  legacy report to make its preferences available again; chat never does so
  implicitly.
- Own-move frame-data answers are neutral about defense; opponent move queries
  still provide verified defensive practice advice. Mirror matches remain
  conservative rather than guessing ownership.
- Progress questions mentioning practice, including whether practice helped or
  worked, use learning evidence. Prospective practice advice remains available.
- Missing requested moments are explicitly unavailable; no loss or action is
  inferred from an absent round.

## Evidence

Full suite: **271 passed**, one existing Starlette/httpx deprecation warning.
Frozen contract examples: **PASS**. Installed dependency check: **No broken
requirements found**. Diff whitespace checks passed.

Each implementation task reproduced its regressions before changing source:
round/numeric tests had ten failures; report/inspection tests had seven;
chat tests had nine. Review follow-ups reproduced five fallback-text failures
and four retrospective practice-routing failures before their corrections.
Focused task suites and the final integrated suite passed afterward.

Provider-disabled HTTP checks copied the committed real live-learning sample
into a temporary directory. Mocked Jev transport scored all 58 menus, with
validated report/save/reload parity and fingerprints on every decision. This is
mocked scoring, not new live provider evidence. Four round tips returned 200
within the word limit. Practice/progress/absent-round chat returned grounded
answers, with analytics deliberately unavailable so local learning fallback was
also exercised. No samples or private recordings were overwritten.

Independent read-only review covered evidence binding, late conflicting rows,
session serialization/cancellation, unchanged-report reuse, move perspective,
intent routing and advice fallbacks. Review follow-ups were fixed and retested.

The in-memory insights schema check additionally validated the described
focus.min_opportunities addition against all eleven existing public fixture
shapes. It rejected missing, zero, negative, fractional, boolean and null values.
This checks the proposed field, not an uninspected implementation commit.
Track C's scoped approval is in INSIGHTS_CONTRACT_APPROVAL.md.

## Remaining runtime acceptance

These checks do not replace an offline Versus rehearsal on the demo host.
Retain evidence for actual round ends, spoken tip timing/fallback, saved sets,
Learning/Stats, replay analysis and Coach citations on the agreed release and
DATA_DIR. Live Jev, OpenAI and Sentry were not called again during these fixes.
Accepted replay B5 evidence and the decision to keep the existing model after
the failed Luna latency gate remain unchanged. Punish metric sign-off and
insights deployment are separate from these replay corrections.

Run from the repository root:

```powershell
.\replay\.venv\Scripts\python.exe -m pytest replay/tests -q
.\replay\.venv\Scripts\python.exe contracts/validate.py
.\replay\.venv\Scripts\python.exe -m pip check
```

Expected: 271 passed, PASS, and No broken requirements found.
