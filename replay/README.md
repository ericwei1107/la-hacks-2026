# Replay and round coach

Track C service: `GET /health`, `POST /coach/round`, `POST /coach/chat`,
`POST /analyze/{session_id}` and `GET /reports/{session_id}` on port 8766.
The request is validated directly against the frozen round-summary JSON schema.
Responses contain only `text` and `severity`, with 1–3 sentences and at most
20 words to fit the between-round voice window. This is stricter than the frozen
contract's under-40-word limit. Post-set reports use Jev to rank character-generated candidates when
available. Post-set chat returns evidence-grounded explanations and round/frame citations.

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
Single prepared tips return immediately without a model call. Optional model
selection has no retries and a 1-second overall deadline; missing keys,
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
Output uses an inspection-specific format, not `contracts/report.schema.json`.
The scored report API described below consumes the same evidence extraction.

The optional real-sample regression test runs when the extracted sample exists;
synthetic edge-case tests run in every checkout:

```powershell
.\replay\.venv\Scripts\python.exe -m pytest replay/tests -q
```

## Post-set report API

`POST /analyze/{session_id}` takes no body. It reads an extracted recording,
validates it, generates options through Claude's
`replay.options.generate_options(human_character, moment)` interface, scores
available menus, and atomically saves `DATA_DIR/reports/<session_id>.json`.
`GET /reports/{session_id}` reads and validates that saved report. Both return
the frozen `contracts/report.schema.json` shape plus evidence and availability
metadata. Missing recordings/reports return 404; invalid IDs, recordings or
saved reports return 422. Reanalysis replaces the report without modifying
the recording. Generation failures leave the previous saved report intact.

The canonical input is `DATA_DIR/recordings/<session_id>.jsonl`. For development,
the resolver also searches extracted `DATA_DIR/samples/**/*.jsonl` by the first
record's session ID. Ambiguous samples return 422; install one canonical
recording to select it. ZIPs are never read as JSONL or extracted by the API.
Session metadata comes from `DATA_DIR/sessions/<session_id>.json`, or a sample's
adjacent `.session.json`. Missing or invalid metadata produces `result: unknown`.
Synthetic directories or session metadata label the report `synthetic: true`.

Only explicit `decision_point` events attributed to the human are decision
entries. `actual` retains the recorded action exactly; missing actions become
`unknown` with `recorded_action: null`. Bot tactical choices never supply it.
Round, frame, source JSONL line and original event accompany each decision.
Ambiguous human identity is retained under `unattributed_decisions`. Observed
health-loss windows are separate from causal claims; no avoidable-damage
`cost` is invented. `went_well` cites observed hits, blocks or throw breaks,
not presumed improvements. `good` is omitted because action/outcome labels
are not reliably equivalent to option IDs.

Habits are the three most frequent recorded situation/action pairs. Their
`count` is observed, and `p` is the empirical action frequency among labeled
decisions in that situation, explicitly identified by `p_source`. These are
observations, not proof of a weakness. Mastery is read from the latest valid
same-session snapshot in `DATA_DIR/learning/<session_id>.jsonl`, limited to
rounds present in the analyzed recording. Each value retains path, round and
line in `mastery_evidence`. It is a learner estimate, not observed success or
proof of improvement. Missing latest values are omitted without carrying an
older habit value forward. Missing files, invalid rows, a truncated final write
and stale snapshots are identified in limitations; mixed session IDs prevent
using the file. Invalid snapshots do not discard other valid snapshots.
Counterfactual minimum changes are not inferred.
Drills direct review of the cited decisions and comparison in practice.

Configuration:

| Variable | Default | Meaning |
|---|---|---|
| `KUMITE_JEV_MODE` | `auto` | `local` disables every Jev request, independently of the round coach |
| `TYPESAFE_API_KEY` | `JEV_API_KEY`, then unset | Credential for TypeSafe Jev |
| `JEV_MODEL` | `jev-latest` | TypeSafe model |

The adapter uses the [official TypeSafe HTTP API](https://docs.typesafe.ai/primitives/choice)
at `https://api.typesafe.ai/v1/systemone` through the already-pinned HTTPX
dependency. No new SDK installation is required. It batches up to 12 choices
per request with one context per choice, a 22-second request deadline, and no
retries. Only recorded decision context is sent; future health-loss windows,
session metadata and credentials are excluded from the state. Snapshot timing
does not prove pre-action state. Candidate limitations are preserved. Choice
keys, finite numeric probabilities, normalization and the selected maximum are
validated; invalid responses are discarded, never repaired or renormalized.
These probabilities describe model preference among candidates, not hit/win
chances or a guarantee that the top move is legal at that exact frame.

Missing keys/options/context, timeouts and invalid responses retain the action
and evidence with `best: unavailable`, `options: []`, and an explicit
`scoring.status: unavailable` reason. Candidate menus without probabilities
remain under `candidates` when available. A failed batch does not discard valid
scores from other batches. POST analysis has no between-round 8-second budget;
`POST /coach/round` keeps its existing deadline and behavior.

The neutral sample is already extracted locally. In a fresh checkout, extract
it once into an empty destination; do not overwrite an existing extraction:

```powershell
Expand-Archive -LiteralPath data/samples/versus_djin_vs_kaz_l3_neutral.zip -DestinationPath data/samples/versus_djin_vs_kaz_l3_neutral
.\replay\.venv\Scripts\python.exe contracts/validate.py data/samples/versus_djin_vs_kaz_l3_neutral/versus_djin_vs_kaz_l3_neutral.jsonl
```

Start offline for repeatable, free verification:

```powershell
$env:KUMITE_JEV_MODE = 'local'
$env:KUMITE_COACH_MODE = 'local'
.\replay\.venv\Scripts\python.exe -m uvicorn replay.main:app --host 127.0.0.1 --port 8766
```

In a second terminal:

```powershell
$sessionId = '2026-10-18T01-24-57_sahil_djin_vs_kaz'
Invoke-RestMethod http://127.0.0.1:8766/health
$report = Invoke-RestMethod -Method Post "http://127.0.0.1:8766/analyze/$sessionId"
$report.scoring_summary
$report.decision_points.Count
Invoke-RestMethod "http://127.0.0.1:8766/reports/$sessionId"
.\replay\.venv\Scripts\python.exe -m pytest replay/tests -q
.\replay\.venv\Scripts\python.exe contracts/validate.py
```

Expected offline: 59 decision points, 0 scored, 59 unavailable, result
`win 3-1`, and matching saved/returned reports. The neutral recording contains
12,147 state records, 282 events, 372 bot tactical choices (220 default,
152 reflex), and one plan. It has 59 explicit human decisions but no round
summaries or learning records. Neither the upcoming live set nor PR #8's
synthetic files are assumed present in this checkout.

For live scoring after approving transmission of recorded contexts to TypeSafe,
restart with `$env:KUMITE_JEV_MODE = 'auto'` and a configured key, then repeat
POST analysis. Its result reports actual scoring availability rather than
promising all decisions will score. Automated tests always disable Jev or use
HTTPX mock transports; the optional extracted-sample test also runs offline.

## Learning and move-specific coaching

Round tips now resolve matching `biggest_moments[].move_id` against the bot's
character data, or resolve the bot move in `after_block:<move>`. Compact labels
such as `b4` are matched only when a single stored command agrees. Unknown and
shared IDs are not guessed. Moments from unrelated situations, explicit
non-bot actors and non-throw moves labeled as throws cannot name a bot move.
Move names come from Claude's lookup interface; those files remain unchanged.

Verified lows produce a named crouch-blocking drill. Plus-on-block entries in
the matchup notes produce a named guarding reminder. Other after-block tips
name the bot move while preserving the uncertainty about punish range and
timing; they do not invent a punish. Verified throws can name the recorded
character-data break input. Missing data retains generic templates. The
provider can select only a prepared grounded sentence, so it cannot introduce
a move name or change the guidance. Round responses are capped at 20 words;
optional model selection has a one-second deadline and a 0.9-second HTTP timeout.
The frozen under-eight-second, under-40-word contract is unchanged. These are
server-side budgets, not a guarantee about venue network or TTS latency.

Fixed low-defense wording is now: "You've fixed your low blocking. Keep
practicing; I'll test it again later." Praise requires the summary's fixed
marker; a mastery estimate alone does not trigger it.

When Sahil's live sample lands, start the service with its DATA_DIR layout:

```powershell
$env:DATA_DIR = './data/samples/live_learning'
$env:KUMITE_JEV_MODE = 'local'
$env:KUMITE_COACH_MODE = 'local'
.\replay\.venv\Scripts\python.exe -m uvicorn replay.main:app --host 127.0.0.1 --port 8766
```

Then analyze the exact session Sahil supplies:

```powershell
$sessionId = (Get-ChildItem data/samples/live_learning/recordings -Filter *.jsonl | Select-Object -First 1).BaseName
$report = Invoke-RestMethod -Method Post "http://127.0.0.1:8766/analyze/$sessionId"
$report.habits | Select-Object situation, action, count, mastery, mastery_evidence
Invoke-RestMethod "http://127.0.0.1:8766/reports/$sessionId"
.\replay\.venv\Scripts\python.exe -m pytest replay/tests -q
.\replay\.venv\Scripts\python.exe contracts/validate.py
```

Expect mastery only for situations present in the latest valid snapshot, with
source evidence. The live sample was absent from main at `843dcb1`; this
follow-up was verified offline against PR #8's explicitly synthetic DATA_DIR
bundle (35 human decisions, round-3 mastery, and three round summaries), plus
unit tests. Synthetic values are not measured player learning. The real
`live_learning` recording still needs an integration check after it lands.

## Coach chat

`POST /coach/chat` accepts `{session_id, player, message, history}` and returns
only `{text, citations: [{frame, round}]}`, following `contracts/api.md`.
History entries use `role: user` or `role: coach`, with `text`. The SDK boundary
maps `coach` to `assistant`. The client supplies earlier messages for the selected
set; the service stores no conversation state. History helps interpret follow-up
questions but is never treated as factual game evidence. `player` is display
context, not authentication or proof of who appears in the recording.

Chat reads the extracted session recording and any saved contract-valid report.
It never triggers analysis or Jev implicitly. Missing reports still permit
recording and character-data questions; absent scores are identified. Missing
recordings return 404, invalid recordings return 422, and malformed chat requests
return 422. Synthetic sessions are labeled in every answer. Known records with
non-finite numeric values are rejected.

The read-only tools are `get_habits`, `get_mastery`, `find_moments`,
`get_state_at`, `get_frame_data`, `list_punishers`, and `get_learning_curve`.
All are scoped to the selected set. Original decision labels supply actions;
bot choices and input buttons do not supply human intent. Counts use decisions
with exact, unambiguous human context. Stale or conflicting snapshots are marked
uncertain; exact-state queries do not quietly choose a nearby or conflicting
snapshot. Frame counters reset each round, so citations contain both values.
Health values are not avoidable damage. Saved Jev preferences must agree with
the original decision and current verified option menu; probabilities retain
their preference meaning and candidate limitations.

Frame-data answers name only uniquely verified moves belonging to characters
in the recording. Hypothetical punishers come from the human's character data
and explicitly leave range, timing and string completion unverified. Mastery
comes from validated local learning snapshots. `get_learning_curve(session)`
calls `GET /learning/{session}` at `KUMITE_ANALYTICS_URL` (default
`http://127.0.0.1:8767`), validates the frozen metrics schema/session, and uses
only recorded rounds. Analytics has a 1.2-second overall deadline, no redirects,
and a local-estimate fallback. Learning or frame-data facts without recorded
frame evidence have empty citations; frame numbers are never invented to fill
the response. Learner estimates do not prove improvement.

In `KUMITE_COACH_MODE=auto` with `OPENAI_API_KEY`, chat uses the installed
OpenAI SDK's [Responses function-calling interface](https://developers.openai.com/api/docs/guides/function-calling)
with `OPENAI_CHAT_MODEL` (default: the configured coach model). The agent can
make up to three model calls and eight tool calls, with a four-second per-call
HTTP timeout, no retries, and an eight-second overall provider deadline.
It selects up to three server-prepared fact IDs; the service renders those
verified sentences and citations. Free-form model prose, unknown IDs, refusals,
invalid tool arguments, API errors and timeouts cannot introduce new claims or
move names. Provider failure uses deterministic local retrieval. This trades
unrestricted prose for bounded, auditable answers.

`KUMITE_COACH_MODE=local` disables chat model calls as well as round-tip model
selection. Learning questions can still read the configured analytics service.
Inputs allow a 4,000-character question and up to 100 history entries of 4,000
characters; the model sees only the last eight entries, each limited to 2,000
characters. Replies contain at most three complete evidence facts and 2,400
characters; oversized facts are replaced with a clarification rather than cut
mid-claim. This post-set budget is separate from the 20-word/one-second round-tip
budget. No new packages are required, and existing round/report routes remain
unchanged.

Run from the repository root with the already extracted neutral sample:

```powershell
$env:DATA_DIR = './data'
$env:KUMITE_COACH_MODE = 'local'
$env:KUMITE_JEV_MODE = 'local'
.\replay\.venv\Scripts\python.exe -m uvicorn replay.main:app --host 127.0.0.1 --port 8766
```

In another terminal:

```powershell
$question = @{
    session_id = '2026-10-18T01-24-57_sahil_djin_vs_kaz'
    player = 'sahil'
    message = 'Show my low-defense decisions'
    history = @()
} | ConvertTo-Json -Depth 6
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8766/coach/chat -ContentType 'application/json' -Body $question
.\replay\.venv\Scripts\python.exe -m pytest replay/tests -q
.\replay\.venv\Scripts\python.exe contracts/validate.py
```

Expect a factual answer about the logged human decisions and citations to real
round/frame coordinates. Try `What do I do after his b4?` for verified move data,
or `Have I improved?` for learning availability. Local answers have no model
charges; analytics failures clearly mark the learning curve unavailable. Set
`KUMITE_COACH_MODE=auto` and restart for optional model-guided retrieval. Automated
checks use mocked Responses/analytics transports; paid live-model and ElevenLabs
voice verification are separate integration checks.
