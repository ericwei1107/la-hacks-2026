# Show the fine-tune before/after on the learning panel (from Eric)

Sahil is fine-tuning Laya on the day's recordings. Its held-out prediction accuracy, before and after the fine-tune, is the Model Learning track's strongest number and the closing shot of the demo video (design doc section 3, 2:05–2:20).

## Data

`GET /learning/{session_id}` on :8767 already returns it (your `LearningMetrics.finetune` type in `app/src/renderer/src/services/contracts.ts`):

```json
"finetune": {"before": 0.41, "after": 0.68}
```

Both values are `null` until Sahil supplies them, which is the normal state today.

## What to show (suggestion; it's your design system)

- When both are numbers: a large before → after pair on the learning screen (`main-window/screens/Learning.tsx`), e.g. "Laya fine-tune 41% → 68% held-out accuracy", plus the gain in points.
- When either is `null`: hide the block, or show a quiet "fine-tune pending" state; never show 0%.
- Readable on video: large numbers, one idea, matching the prediction-accuracy chart.

## Test it without Sahil

Run the mock or real analytics service, then drop a test file:

```
mkdir -p data/eval && echo '{"before": 0.41, "after": 0.68}' > data/eval/2026-10-17T13-05-00_synth_djin_vs_kaz.json
```

`/learning/2026-10-17T13-05-00_synth_djin_vs_kaz` then returns it without a restart. Delete the file afterwards; these are test values, not real results.

`/team-status` closes this item automatically once `finetune` is used in an `app/` screen.
