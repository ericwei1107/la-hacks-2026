# Replay and round coach

First Track C milestone: `GET /health` and `POST /coach/round` on port 8766.
The request is validated directly against the frozen round-summary JSON schema.
Responses contain only `text` and `severity`, with 1–3 sentences and fewer than
40 words. This milestone does not implement replay reports, Jev scoring, or chat.

## Windows setup

Run from the repository root. The environment is private to `replay/` and does
not require activation or changes to PowerShell's execution policy.

```powershell
py -3.13 -m venv replay/.venv
.\replay\.venv\Scripts\python.exe -m pip install -r replay/requirements.txt
```

The local environment uses your installed Python 3.13 interpreter.
`requirements.in` lists direct dependencies;
`requirements.txt` pins the installed environment, including test dependencies.

## Run

```powershell
.\replay\.venv\Scripts\python.exe -m uvicorn replay.main:app --host 127.0.0.1 --port 8766
```

The service loads the repository root `.env` without overriding existing process
variables. Secrets are never included in responses. Configuration:

| Variable | Default | Meaning |
|---|---|---|
| `DATA_DIR` | repository `data/` | Shared data directory; relative paths resolve from the repository root |
| `KUMITE_COACH_MODE` | `auto` | `auto` enables the model when a key is present; `local` always uses the deterministic coach |
| `OPENAI_API_KEY` | unset | Enables the optional model call |
| `OPENAI_COACH_MODEL` | `OPENAI_MODEL`, then `gpt-4.1-mini` | Model used for the between-round call |
| `KUMITE_VERSION` | current Git commit SHA | Health response version; set when deploying without `.git` |

The model makes one structured selection among grounded tips prepared from the
summary. It cannot introduce moves, invented counts, or unverified frame-data
advice. This intentionally avoids depending on character files while Claude
finishes them. The SDK's structured parsing follows the
[official OpenAI documentation](https://developers.openai.com/api/docs/guides/structured-outputs).
Model calls have no retries and a 5-second overall deadline; missing keys,
timeouts, API errors, refusals, or invalid output use the local tip. A warning
records fallback without logging provider errors or keys. Local mode makes no
external calls. `p` is a probability estimate, not an observed hit count;
the coach never multiplies it by `n` to invent a count.

## Verify

With the server running, open a second PowerShell terminal at the repository root:

```powershell
Invoke-RestMethod http://127.0.0.1:8766/health
$summary = Get-Content contracts/examples/round_summary.json -Raw
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8766/coach/round -ContentType 'application/json' -Body $summary
```

Health should show `ok: True`, `service: replay`, and the current Git SHA.
The example should return `severity: warn` and a brief tip about crouch-blocking
predictable lows. Model wording can differ from the local fallback.

For repeatable verification without using API credits, set local mode before
starting the server:

```powershell
$env:KUMITE_COACH_MODE = 'local'
```

Run automated checks without a running server:

```powershell
.\replay\.venv\Scripts\python.exe -m pytest replay/tests -q
.\replay\.venv\Scripts\python.exe contracts/validate.py
```

Tests use the contract example, malformed inputs, forward-compatible fields,
fixed habits, sparse evidence, CORS, and simulated provider failure/latency.
They do not make paid API calls. The service returns HTTP 422 for summaries
that fail the frozen schema. `/docs` provides the interactive API reference.

## Recording integration notes

The future coach-agent tool `get_learning_curve(session)` must call
`GET /learning/{session_id}` on Eric's analytics service, port 8767.
Use `KUMITE_ANALYTICS_URL` as its base URL (normally `http://127.0.0.1:8767`)
and the response format in `contracts/metrics.schema.json`. This tool is not
implemented in the current round-coach milestone.

The game team reports that `kind: decision_point` events use `actor` for the
human's slot and populate the top-level `situation` and `action` fields. Future
readers should consume these explicit human decision labels and identify the
human by `human_slot`, never by assuming slot 0.

Bot decisions are recorded as `t: tactical`, including `source: reflex`,
`source: default`, and `source: habit`. Future replay readers must preserve these sources and accept
unrecognized source values for forward compatibility. Do not count tactical
records as the human's chosen actions. The source list in
`contracts/recording.md` currently omits `reflex`; only the team can approve a
change to that frozen contract. The current contract validator skips tactical
records, so a passing validation does not validate their contents.

The game team reports these shapes exist as of commit `8018810`: one
`round_summary` at every round end; `learning_event` records with `event` equal to
`fixed`, `regressed`, or `player_changed`; explicit human decision-point labels;
and `learning_round` lines in `data/learning/`. Those shapes can be integrated now;
the upcoming audit is expected to change numbers, not shapes. Inspection of that
commit confirms the learning-event discriminator is `event`, not `kind`.
However, `8018810` was not an ancestor of the fetched `origin/main` at `48545f7`
when the coaching branch was synchronized. New sample availability must still be
verified directly. The current round endpoint is verified against
`contracts/examples/round_summary.json`, not a newly recorded round summary.

The game team's sample is distributed as
`data/samples/versus_djin_vs_kaz_l3.zip`. Extract its JSONL before passing it to
the contract validator or a recording reader:

```powershell
Expand-Archive -LiteralPath data/samples/versus_djin_vs_kaz_l3.zip -DestinationPath data/samples/versus_djin_vs_kaz_l3
Get-ChildItem data/samples/versus_djin_vs_kaz_l3 -Recurse -Filter *.jsonl | ForEach-Object {
    & .\replay\.venv\Scripts\python.exe contracts/validate.py $_.FullName
}
```

The versus archive was retrieved from `origin/main` at `7bac2fa` and extracted
to the directory above. Contract validation passed with 15,108 state records,
305 event records, and 281 tactical records. That recording contains no
`round_summary` records; it does not establish availability of the later
round-summary or learning samples. The downloaded ZIP and extracted samples
have not been added to a new commit on Garrett's branch.

## Local recording inspection

Generate an observation report from an extracted recording, without Jev or any
model calls:

```powershell
.\replay\.venv\Scripts\python.exe -m replay.inspect data/samples/versus_djin_vs_kaz_l3/versus_djin_vs_kaz_l3.jsonl
```

The CLI writes `<session>.inspection.json` and `<session>.inspection.md` under
`DATA_DIR/inspections/` (normally `data/inspections/`). Open the Markdown file to
review the moments, and use the JSON for downstream development. Pass
`--output-dir PATH` to choose another directory. Existing reports are protected;
pass `--overwrite` explicitly to regenerate them. ZIP input produces extraction
instructions rather than attempting to read binary data as JSONL.

Each moment includes its round, frame, original JSONL line, event evidence,
human/opponent roles, nearby state context, logged event damage, and a separate
following-60-frame health-loss window. Unknown actions, situation labels, missing
states, incomplete frame coverage, and health increases are marked. Frame numbers
reset each round; seconds derived from those counters are not video timestamps.
Health-loss windows may overlap, so do not sum them or call their damage avoidable.
No move names, punish recommendations, probabilities, or best options are invented.

The real sample yields 291 observed moments: 59 human hit/counter-hit events,
143 human attacks blocked by the bot, 10 human whiffs, plus landed hits,
knockdowns, throws and breaks. Its 281 bot reflex choices remain separate from
human actions. It has no explicit human decision labels or round summaries.

The reader validates known record schemas, preserves source line numbers, ignores
unknown record types, and accepts new tactical source values. A truncated final
write is ignored with a warning; malformed interior records, invalid known
records, duplicate player slots, and mixed session IDs fail with a line number.
Output uses an inspection-specific format, not `contracts/report.schema.json`;
the future scored report and API endpoints remain separate work.

The optional real-sample regression test runs when the extracted sample exists;
synthetic edge-case tests run in every checkout:

```powershell
.\replay\.venv\Scripts\python.exe -m pytest replay/tests -q
```

## Follow-up after Jev

Make the coach specific using recorded `biggest_moments[].move_id` and the bot's
`characters/<bot>/moves.json`: resolve the move name, resolve the bot move in
`after_block:<move>`, and retrieve the one-line fix from matchup notes. Have the
LLM compose the sentence from those facts, validate every named move against the
move list, and retain templates as the fallback. For a genuinely fixed low-defense
habit, prefer spoken wording such as "You've fixed your low blocking. I'll test
it again later." over "marked as improved". This is planned follow-up, not current
endpoint behavior.
