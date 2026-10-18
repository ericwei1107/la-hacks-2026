# PRs #19/#20: integration review

Reviewed October 18, 2026 on Eric's local branch, with Eric's in-progress backend/export changes present.

PR [#20](https://github.com/ericwei1107/la-hacks-2026/pull/20), merged by Garrett, contains Chloe's app work. The updated branch also includes PR [#19](https://github.com/ericwei1107/la-hacks-2026/pull/19), her reserved readiness checker and tests. The branch fast-forwarded from `dc1f90c` to `c87dcbe67485f23ad8c81b6fbb8c2737f6ac3c49` without conflict. The 34 incoming paths did not overlap any in-progress path. SHA-256 comparisons confirmed that all 27 existing modified/untracked files were preserved byte-for-byte immediately after integration. No unmerged index paths remain.

Neither PR changes frozen contracts, game/replay services or mock behavior. The app continues to use existing endpoints; the proposed insights route remains unregistered. Team status refreshed successfully before integration. It reports an unrelated conflict with the older `origin/garrett/replay-inspection` branch in `replay/SENTRY_VERIFICATION.md`; that branch was not merged here.

## Local validation

- `cd app && npm run build`: passed, including both TypeScript checks and Electron/Vite production builds.
- `SENTRY_DSN= DATABASE_URL= .venv/bin/python -m unittest discover -s analytics/tests -p test_insights.py -v`: 31 passed after integration.
- `SENTRY_DSN= DATABASE_URL= .venv/bin/python -m unittest discover -s analytics/tests -p test_integration_check.py -v`: 15 passed with local HTTP access. The initial sandboxed run could not bind temporary test servers; the rerun had no test failures.
- `SENTRY_DSN= DATABASE_URL= .venv/bin/python -m unittest discover -s analytics/tests -v`: 140 cases, 139 passed and one opt-in cloud skip on the combined branch. This passing suite does not cover the reset sequence below.
- Chloe's [static real-fixture app acceptance](../../app/docs/acceptance/2026-10-18-stats-learning.md) is owner-supplied evidence. It leaves growing-session flushes and live-session refresh unexercised. This review did not perform a new native visual/audio/game rehearsal.

## C1 owner follow-up: reset after partial advancement

The checker remembers each endpoint's highest reached round even after that endpoint resets. This can produce a successful advancement verdict without a currently shared later round:

| Observation | Stats latest | Learning latest |
| --- | --- | --- |
| Initial | 4 | 4 |
| First poll | 5 | 4 |
| Second poll | 4, reset | 5 |

Actual: exit 0, `advanced: true`, remembered reached values 5/5, while current stats still ends at 4. The report lists the reset, but the success calculation ignores it. Expected: no successful advancement from that sequence. Chloe should invalidate accumulated advancement when a source resets, or require an appropriate currently shared later completed round, while continuing to allow separate file flushes. Add a regression in her reserved checker test file. This is a PR #19 correctness follow-up, not a merge conflict or a blocker for independent Eric backend work. Do not use the current advance-required success alone for final host acceptance.

Reproduce from the repo root without servers or external calls:

```sh
.venv/bin/python - <<'PY'
from unittest.mock import patch
from analytics import integration_check as checker

class Clock:
    now = 0.0
    def clock(self):
        return self.now
    def sleep(self, seconds):
        self.now += seconds

clock = Clock()
values = {'stats': iter([4, 5, 4]), 'learning': iter([4, 4, 5])}
def read(kind, *args):
    return {'status': 'ok', 'rounds': list(range(1, next(values[kind]) + 1))}

with patch.object(checker, 'check_health', return_value={'status': 'ok'}), patch.object(checker, 'read_rounds', side_effect=read):
    report = checker.run('test', dict.fromkeys(checker.SERVICES, 'http://localhost'), watch_seconds=1, poll_seconds=.1, require_advance=True, clock=clock.clock, sleep=clock.sleep)
print(report['exit_code'], report['advance'])
PY
```

Expect the current defect to print `0` and an advancement report containing `stats went back from round 5 to 4`. After Chloe's correction, this sequence must not return a successful advancement verdict.
