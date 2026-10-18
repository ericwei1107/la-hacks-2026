# Live learning set (M3 step 4)

A real versus set recorded on Sahil's laptop on 2026-10-18: Devil Jin (human, P1) against the Kumite bot playing Kazuya at difficulty 3, with the detector, the four learners and the tactical layer running live. Nothing in this folder is synthetic.

Session: `2026-10-18T05-14-03_sahil_djin_vs_kaz`. Result: loss 1-3 (rounds won by the bot, bot, human, bot). 10,080 states, 238 events, 58 human decision points, 231 tactical decisions (33 habit-driven), 4 round summaries, 4 learning rounds, 2 learning events.

Layout matches `data/samples/synthetic/`, so it works as a `DATA_DIR`:

```
recordings/2026-10-18T05-14-03_sahil_djin_vs_kaz.jsonl
sessions/2026-10-18T05-14-03_sahil_djin_vs_kaz.json
learning/2026-10-18T05-14-03_sahil_djin_vs_kaz.jsonl
profiles/sahil_devil_jin.json
```

The profile is the snapshot after this set. Its predictor pickle is not shipped, so `predictor` is null here.

## What it shows

- **Low habit detected.** The human was hit by every plain low the bot landed: 16 of 16, none blocked. The low_defense habit became active on its fourth sample, at the start of round 3.
- **Low exploited.** From round 3 the low class carried a x1.9 boost. Mean low weight per round went 0.56, 0.59, 1.03, 1.15; low picks went 6, 8, 8, 17, with 17 of round 4's lows chosen by the habit.
- **A fixed and a regressed event.** after_block:any was marked fixed in round 2 after correct punishes on blocked df+2, then regressed early in round 3.
- **Prediction accuracy per round:** 0.60, 0.73, 0.90, 1.00.

## What it does not show

The low habit is never fixed. The plan was to stop crouch-blocking after two rounds, but no low in rounds 3 or 4 was blocked, and the stick never touched down-back or down in the 25 frames before any low connected. low_defense mastery stays at 0.17 with 15 observations. A set that blocks lows from round 3 is still needed to show a live low_defense fixed event.

## Check it

From the repo root:

```sh
python contracts/validate.py data/samples/live_learning/recordings/2026-10-18T05-14-03_sahil_djin_vs_kaz.jsonl
python contracts/validate.py data/samples/live_learning/learning/2026-10-18T05-14-03_sahil_djin_vs_kaz.jsonl
python -m game.summarize data/samples/live_learning/recordings/2026-10-18T05-14-03_sahil_djin_vs_kaz.jsonl
```

Both validations print PASS. The summary ends with the four round summaries, the two learning events and the per-round learning table.
