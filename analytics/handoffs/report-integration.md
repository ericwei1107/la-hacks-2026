# Report integration: exact PR #8 synthetic fixture

## Track D local acceptance — October 18, 2026

`analytics/tests/report_smoke.py` ran the actual replay FastAPI service over loopback HTTP against temporary copies of the synthetic and real M3 bundles. Schema validation, POST analysis / saved GET equality and source preservation passed. Synthetic: 35 decision points and 59 checked source citations; real: 58 decision points and 101 checked citations. All returned decisions were honestly labelled unscored, with `best=unavailable` and no model option probabilities. The test disabled OpenAI/Jev keys, database and Sentry and shut down both child processes.

This local check used the root Python environment plus replay's pinned OpenAI SDK installed in an isolated temporary directory. With replay requirements available in the chosen environment, repeat `python analytics/tests/report_smoke.py`. Native Windows host integration and actual Jev/provider activity remain separate; the new insight export does not trust report revision identity or use report recommendations yet.

The published `replay/` implementation exposes health, round coaching, `/analyze/{session_id}` and `/reports/{session_id}`. Local runtime acceptance is recorded above; the commands below remain the owner-host reproduction path. Mastery/learning interpretation remains separate work, and mock reports are a separate implementation.

PR #8 is merged as `843dcb1d3f8ca231ee1fdb163ce690e66f48e550`; it includes the following single synthetic bundle. It is generated test data, not measured model learning or fine-tune performance.

Session id: `2026-10-17T13-05-00_synth_djin_vs_kaz`

| Purpose | Exact repository path |
|---|---|
| Recording, including three `round_summary` records | `data/samples/synthetic/recordings/2026-10-17T13-05-00_synth_djin_vs_kaz.jsonl` |
| Session metadata | `data/samples/synthetic/sessions/2026-10-17T13-05-00_synth_djin_vs_kaz.json` |
| Three companion learning records | `data/samples/synthetic/learning/2026-10-17T13-05-00_synth_djin_vs_kaz.jsonl` |
| Profile | `data/samples/synthetic/profiles/synth_devil_jin.json` |

Set `DATA_DIR=./data/samples/synthetic` for each service. The metadata identifies `player=synth`, human Devil Jin in slot 0, bot Kazuya, difficulty 3, three rounds and `result=loss 1-2`. The recording has 5,400 states, 93 events, 20 tactical records, three plans and three summaries. Learning accuracy 0.41 → 0.58 → 0.71, detection in round 1 and mastery in round 3 are planted synthetic values. Fine-tune values remain null.

## Run and check

For mock brain with a real report service, run only the brain mock on 8765, leaving 8766 for the report owner's service:

```sh
DATA_DIR=./data/samples/synthetic .venv/bin/python tools/mock/serve.py --services brain
```

Start the owner's published report implementation with the same `DATA_DIR`, then exercise the existing frozen routes:

```sh
curl -fsS http://localhost:8765/sessions
curl -fsS -X POST http://localhost:8766/analyze/2026-10-17T13-05-00_synth_djin_vs_kaz
curl -fsS http://localhost:8766/reports/2026-10-17T13-05-00_synth_djin_vs_kaz
```

Expect the synthetic session in the list, a contract-valid report from analysis and the same saved report from GET. Identify every decision-count denominator and observed-frequency numerator/denominator. Check citations against actual recording round/frame pairs. Do not convert learning `p` estimates into observed counts or infer mastery from observed frequencies. Mastery/learning integration is not a completion requirement for this report-only check.

To inspect analytics separately:

```sh
DATA_DIR=./data/samples/synthetic SENTRY_DSN= DATABASE_URL= .venv/bin/python -m uvicorn analytics.main:app --host 127.0.0.1 --port 8767
curl -fsS http://localhost:8767/learning/2026-10-17T13-05-00_synth_djin_vs_kaz
```

The learning response should match the planted values above. It does not imply that the report implementation consumes them. Sahil's real sample has since passed analytics intake; see [B4 results](../LIVE_LEARNING_VERIFICATION.md).

## Reply to forward

PR #8 is merged. Use session `2026-10-17T13-05-00_synth_djin_vs_kaz` and `DATA_DIR=./data/samples/synthetic`. The recording, session metadata and learning filenames are the session id with `.jsonl`, `.json` and `.jsonl` extensions under that directory's `recordings/`, `sessions/` and `learning/`; the profile is `profiles/synth_devil_jin.json`. The table above gives the full paths. This is a generated three-round fixture, so keep counts/frequencies labelled as synthetic. Track D's local actual-service checks now pass; owner-host/native integration remains pending.
