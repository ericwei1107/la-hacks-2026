# Fine-tune before/after for the learning panel (from Eric)

You own the Laya harness, the dataset, the fine-tune and the before/after eval. The analytics service already serves the result as `finetune` in `GET /learning/{session_id}` (`contracts/metrics.schema.json`). It just needs a file to read.

## Where to write it

`DATA_DIR/eval/<session_id>.json`, one file per session the result should show on:

```json
{"before": 0.41, "after": 0.68}
```

- Both keys are required. Each is `null` or a number between 0 and 1: held-out prediction accuracy before and after the fine-tune.
- `<session_id>` must match a session the service knows (`DATA_DIR/sessions/<id>.json`, or a sample in `data/samples/`).
- Write it atomically (write a temp file, then rename), because the service rereads it whenever it changes. No restart is needed.
- Missing file: `before` and `after` are `null`. An invalid file makes `/learning` return 503 with the reason, so check it with `curl localhost:8767/learning/<id>`.
- The mock (`tools/mock/serve.py`) reads the same file, so the app behaves the same against both.
- Fields on learning records do not supply this value; only the eval file does.

## Check

```
mkdir -p data/eval && echo '{"before": 0.41, "after": 0.68}' > data/eval/<session_id>.json
curl -s localhost:8767/learning/<session_id> | python -c "import json,sys; print(json.load(sys.stdin)['finetune'])"
```

Expected: `{'before': 0.41, 'after': 0.68}`.

`/team-status` closes this item automatically once `game/` writes under `eval/`.
