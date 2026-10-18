# Fine-tune before/after for the learning panel (from Eric)

**Delivered October 18 (code `561bcb0` on main):** `python -m game.finetune eval` writes `DATA_DIR/eval/2026-10-18T07-30-06_sahil_djin_vs_kaz.json` with `before`/`after` = balanced accuracy (0.45 → 0.50; majority baseline 0.40) plus extra detail fields. Track D verified that this record shape is served unchanged by `GET /learning/{session_id}` as `finetune`. The panel display is Chloe's request (`finetune-panel.md`).

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

`/team-status` detects a JSON result path in committed `game/` code using this form (on one line; either quote style works):

```python
eval_path = data_dir / "eval" / f"{session_id}.json"
```

It reports `on_branch` until that code reaches `origin/main`, then `on_main`. An `"eval"` CLI command alone leaves the item `pending`. This is a source-code signal; it does not verify that the writer ran, wrote atomically, or produced valid results. Use the `/learning` check above to confirm the actual file. If the writer uses a different path construction, update the check to match it.
