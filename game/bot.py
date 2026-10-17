import argparse
import random
import sys

from game.difficulty import Difficulty
from game.hotloop import Hooks, run_session
from game.notation import Timing
from game.pad import KillSwitch, connect_pad, load_config
from game.reader import Reader
from game.readout import run_gate
from game.record import add_session_args
from game.reflex import Reflex, load_punishers
from game.sequencer import Sequencer


class BotHooks(Hooks):
    def __init__(self, pad, difficulty, seed=None, config=None):
        self.pad = pad
        self.difficulty = difficulty
        self.rng = random.Random(seed)
        self.config = config or load_config()
        self.seq = None
        self.reflex = None

    def start(self, snap, sid):
        bot = 1 - snap.human_slot
        character = snap.players[bot]["character"]
        latency = self.config["input_latency_frames"]
        timing = Timing.from_config(self.config.get("timing"))
        self.seq = Sequencer(self.pad, latency, self.difficulty, self.rng, timing)
        punishers, source = load_punishers(character)
        self.reflex = Reflex(self.seq, self.difficulty, latency, punishers, self.rng)
        tiers = ", ".join(f"{s}: " + " ".join(f"{t['notation']}(i{t['startup']})" for t in punishers[s]) for s in ("standing", "crouching"))
        print(f"bot P{bot + 1} {character} at difficulty {self.difficulty.level} "
              f"(reaction {self.difficulty.reaction_delay_frames}f, frame-perfect {self.difficulty.frame_perfect_chance:.0%}, "
              f"accuracy {self.difficulty.punish_accuracy:.0%}, execution error {self.difficulty.execution_error:.0%}), "
              f"latency {latency}f; punishers from {source}: {tiers}. Kill key {self.config['kill_key']}.", flush=True)

    def poll(self):
        self.pad.check_kill()

    def frame(self, state, events):
        records = self.reflex.step(state, events)
        bot = state["players"][1 - state["human_slot"]]
        self.seq.on_frame(state["frame"], bot, self.reflex.live(state))
        self.seq.pop_finished()
        return records

    def close(self):
        if self.seq is not None:
            self.seq.cancel()
        self.pad.release_all()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kumite bot: reflex layer (block, punish, throw break) on the virtual 2P pad, recording the session")
    add_session_args(parser)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args(argv)

    reader = Reader(args.offsets)
    pad = None
    try:
        if not run_gate(reader, args.offsets):
            return 1
        pad = connect_pad()
        run_session(reader, args, BotHooks(pad, Difficulty.preset(args.difficulty), args.seed))
        return 0
    except KillSwitch as e:
        print(f"stopped: {e}", flush=True)
        return 1
    finally:
        if pad is not None:
            pad.release_all()
        reader.close()


if __name__ == "__main__":
    sys.exit(main())
