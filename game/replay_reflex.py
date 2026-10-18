import argparse
import copy
import random
import sys

from game.difficulty import Difficulty
from game.hotloop import fmt_record
from game.notation import Timing
from game.options import load_options
from game.pad import Controls, load_config
from game.reflex import Reflex, load_punishers, load_wakeups
from game.sequencer import Sequencer
from game.state import Tracker
from game.summarize import load_jsonl
from game.tactical import Tactical


class RecordingPad(Controls):
    remote = False

    def __init__(self, config=None):
        super().__init__(config, kill_key=False)
        self.log = []

    def set_names(self, names):
        names = set(names)
        if names == self.held:
            return False
        self.held = names
        return True

    def release_all(self):
        self.held = set()


def replay(states, difficulty, seed=None, config=None, character=None, tactical=False, options=None):
    config = config or load_config()
    latency = config["input_latency_frames"]
    rng = random.Random(seed)
    pad = RecordingPad(config)
    seq = Sequencer(pad, latency, difficulty, rng, Timing.from_config(config.get("timing")))
    tracker = Tracker(states[0]["session_id"] if states else "")
    reflex = None
    brain = None
    records, events, applied = [], [], []
    for raw in states:
        state = copy.deepcopy(raw)
        evs = tracker.step(state)
        bot_slot = 1 - state["human_slot"]
        if reflex is None:
            name = character or state["players"][bot_slot]["character"]
            reflex = Reflex(seq, difficulty, latency, load_punishers(name)[0], rng, load_wakeups(name)[0])
            if tactical:
                brain = Tactical(seq, difficulty, latency, options or load_options(name)[0], rng)
        recs = reflex.step(state, evs)
        if brain is not None:
            recs = recs + brain.step(state, evs, reflex)
        mask = seq.on_frame(state["frame"], state["players"][bot_slot], reflex.live(state))
        if seq.applied and (not applied or applied[-1] != (state["round"],) + seq.applied[-1]):
            applied.append((state["round"],) + seq.applied[-1])
        records.extend(recs)
        events.extend(evs)
    events.extend(tracker.finish())
    return records, events, applied


def main(argv=None):
    parser = argparse.ArgumentParser(description="Replay a recording through the tracker and the reflex layer (no game, no pad)")
    parser.add_argument("recording")
    parser.add_argument("--difficulty", type=int, default=5, choices=range(1, 6))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--character")
    parser.add_argument("--inputs", action="store_true", help="also print every pad mask change")
    parser.add_argument("--tactical", action="store_true", help="also run the tactical layer (neutral play) as a dry run")
    args = parser.parse_args(argv)

    states = [r for r in load_jsonl(args.recording) if r.get("t") == "state"]
    records, events, applied = replay(states, Difficulty.preset(args.difficulty), args.seed, character=args.character,
                                      tactical=args.tactical)
    lines = [(r["round"], r["frame"], 1, fmt_record(r)) for r in records if r.get("t") == "tactical"]
    lines += [(e["round"], e["frame"], 0, fmt_record(e)) for e in events if e["kind"] not in ("round_start",)]
    if args.inputs:
        lines += [(rnd, frame, 2, f"r{rnd} f{frame:>6} pad          {mask[0]}{'+' + '+'.join(mask[1]) if mask[1] else ''}")
                  for rnd, frame, mask in applied]
    for *_, text in sorted(lines):
        print(text)
    kinds = {}
    for r in records:
        if r.get("source") != "reflex":
            continue
        key = (r["reflex"]["kind"], "miss" if r["reflex"].get("rolled_miss") else r["chosen"])
        kinds[key] = kinds.get(key, 0) + 1
    print(f"{len(states)} states, {sum(kinds.values())} reflex decisions: "
          + ", ".join(f"{k} {c} x{n}" for (k, c), n in sorted(kinds.items())))
    if args.tactical:
        mix = {}
        for r in records:
            if r.get("t") == "tactical" and r.get("source") != "reflex":
                mix[r["chosen"]] = mix.get(r["chosen"], 0) + 1
        print(f"{sum(mix.values())} tactical decisions: " + ", ".join(f"{k} x{n}" for k, n in sorted(mix.items(), key=lambda kv: -kv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
