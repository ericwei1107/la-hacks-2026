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

The game team reports that reflex decisions are recorded as `t: tactical` with
`source: reflex`. Future replay readers must preserve this source and accept
unrecognized source values for forward compatibility. These are bot decisions;
do not count them as the human's chosen actions. The source list in
`contracts/recording.md` currently omits `reflex`; only the team can approve a
change to that frozen contract. The current contract validator skips tactical
records, so a passing validation does not validate their contents.

The game team's sample is distributed as
`data/samples/versus_djin_vs_kaz_l3.zip`. Extract its JSONL before passing it to
the contract validator or a recording reader:

```powershell
Expand-Archive -LiteralPath data/samples/versus_djin_vs_kaz_l3.zip -DestinationPath data/samples/versus_djin_vs_kaz_l3
Get-ChildItem data/samples/versus_djin_vs_kaz_l3 -Recurse -Filter *.jsonl | ForEach-Object {
    & .\replay\.venv\Scripts\python.exe contracts/validate.py $_.FullName
}
```

The sample archive was not present in this checkout when these notes were added.
