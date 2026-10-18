# Replay correctness fixes implementation plan

> For agentic workers: apply the test-first execution and review workflow.

Goal: fix the eight reproduced issues in the approved readiness audit without
changing the frozen API, Claude's files, characters, analytics, tools or app.
The user explicitly authorized these fixes after reviewing that audit.

Architecture: retain verified-fact selection, exact evidence and the existing
timeouts. Add shared decision evidence fingerprints for reports and chat, reject
ambiguous attribution, serialize analysis per session, and correct advice intent
and ownership. Python/FastAPI/pytest; no new dependencies.

## Task 1: round advice and numeric validation

- [x] Add failing regressions in test_service.py/test_move_coaching.py for
  advantageous/unknown after-block pressing and raw NaN/Infinity input.
- [x] Update coach.py so guarding advice requires evidence the human should
  guard; do not label bot-minus pressing a weakness. Validate finite summary
  numbers in main.py before coaching. Keep 20 words and the provider budget.
- [x] Verify the round-coaching and move-coaching suites.

## Task 2: report attribution, provenance and serialization

- [x] Add failing regressions in test_reports.py/test_inspection.py for
  conflicting states, identical duplicates, same-session overlapping analyses
  and independent-session concurrency.
- [x] Make ambiguous same-coordinate states explicitly unattributable in
  inspection; retain raw event evidence without scoring or habit attribution.
- [x] Add replay/evidence.py decision_fingerprint(moment, options): hash a
  versioned canonical JSON object containing all original event evidence,
  context, relevant scorer inputs and candidate id/name/command/description.
  Use allow_nan=False. Reports store evidence_fingerprint on each point.
- [x] Serialize the capture/scoring/save transaction per session, without
  blocking analysis of other sessions; clean up per-session lock bookkeeping.
- [x] Verify report, inspection and relevant existing suites.

## Task 3: chat intent, move ownership and source reuse

- [x] Add failing regressions for progress forms mentioning practice, advice
  on own versus opponent moves, missing requested moments, and stale saved
  scores after state/event/candidate changes.
- [x] Update chat_tools.py (and chat.py only if necessary). Progress questions
  use learning evidence; prospective improvement requests still use practice.
  Offensive own-move queries receive neutral/own-perspective verified facts.
  Empty searches explicitly say no moments matched before report status.
- [x] Import decision_fingerprint(moment, options) from replay/evidence.py;
  accept a saved score only when its stored evidence_fingerprint matches the
  current moment and regenerated menu. Legacy missing fingerprints are
  unavailable; retain the existing menu/distribution checks.
- [x] Verify chat tests, including a fresh unchanged report and changed
  state/event/options. No implicit analysis or Jev call in chat.

## Integration and publication

- [x] Independently review all changes and fix findings.
- [x] Run replay/tests, contracts/validate.py, pip check and diff checks.
- [x] Repeat provider-disabled local HTTP checks on the public real sample
  using disposable report directories. Do not overwrite sample/private files.
- [x] Document compatibility and the contracts-addition decision in replay/
  only. Clarify Eric's unspecified new field separately; do not silently
  approve an unidentified field or enable punish focus.
- [x] Commit only this change's files, push a focused branch and open a PR.
  Preserve unrelated untracked handoff/evaluation/review files.

Execution evidence: 271 replay tests passed, frozen examples PASS, dependency check clean, and provider-disabled real-sample HTTP checks passed with mocked Jev. Independent final review cleared all findings. Publication is recorded by the branch commit and PR.
