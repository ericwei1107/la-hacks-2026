# Synthetic three-round fixture

This bundle is generated demo/test data, not measured model learning or fine-tune results. It contains three 30-second rounds: 5,400 states, 93 events, 20 tactical records, three plans and three summaries, with separate metadata, learning and profile files.

Session: `2026-10-17T13-05-00_synth_djin_vs_kaz`. The planted story is low-defense detection in round 1, mastery in round 3, a bandit preference switch and a player-changed marker. Fine-tune values remain null.

Regenerate deterministically from the repo root:

```sh
.venv/bin/python tools/mock/synth.py --seed 1 --out data/samples/synthetic
.venv/bin/python contracts/validate.py data/samples/synthetic/recordings/2026-10-17T13-05-00_synth_djin_vs_kaz.jsonl
```

Run mock brain/replay in one terminal:

```sh
DATA_DIR=./data/samples/synthetic .venv/bin/python tools/mock/serve.py --services brain,replay
```

Run real analytics in another (omit DATABASE_URL to use files):

```sh
DATA_DIR=./data/samples/synthetic SENTRY_DSN= DATABASE_URL= .venv/bin/python -m uvicorn analytics.main:app --host 127.0.0.1 --port 8767
```

Expected: three healthy services. `/learning/2026-10-17T13-05-00_synth_djin_vs_kaz` shows detection at round 1, mastery at round 3, accuracy 0.41 → 0.58 → 0.71, and null fine-tune values. Every planted value is synthetic.
