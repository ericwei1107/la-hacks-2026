import argparse
import random
import sys

from game import api, trace
from game.coach import Outlet, replay_url
from game.comboplay import ComboPlay, describe as describe_combos, load_play_routes
from game.detect import Detector
from game.difficulty import Difficulty
from game.hotloop import MATCH_OVER, Hooks, run_session, wait_for_match
from game.learning import Learning
from game.notation import Timing
from game.options import CLASSES, load_options
from game.pacer import Pacer
from game.pad import KillSwitch, connect_pad, load_config
from game.reader import Reader
from game.readout import run_gate
from game.record import add_session_args
from game.recorder import data_dir
from game.reflex import Reflex, load_punishers, load_wakeups
from game.sequencer import Sequencer
from game.tactical import Tactical

DEMO_PLAYER = "guest"


class BotHooks(Hooks):
    def __init__(self, pad, difficulty, seed=None, config=None, player="player", fresh=False):
        self.pad = pad
        self.difficulty = difficulty
        self.rng = random.Random(seed)
        self.config = config or load_config()
        self.player = player
        self.fresh = fresh
        self.seq = None
        self.reflex = None
        self.tactical = None
        self.detector = None
        self.learning = None
        self.combos = None

    def start(self, snap, sid):
        bot = 1 - snap.human_slot
        character = snap.players[bot]["character"]
        human_character = snap.players[snap.human_slot]["character"]
        latency = self.config["input_latency_frames"]
        timing = Timing.from_config(self.config.get("timing"))
        self.seq = Sequencer(self.pad, latency, self.difficulty, self.rng, timing)
        punishers, source = load_punishers(character)
        wakeups, wake_source = load_wakeups(character)
        self.reflex = Reflex(self.seq, self.difficulty, latency, punishers, self.rng, wakeups)
        options, option_source = load_options(character)
        self.learning = Learning(self.player, human_character, options, self.difficulty, self.rng, fresh=self.fresh)
        self.tactical = Tactical(self.seq, self.difficulty, latency, options, self.rng, learning=self.learning)
        self.detector = Detector(snap.human_slot, options)
        short, full = load_play_routes(character)
        self.combos = ComboPlay(self.seq, self.difficulty, self.rng, (short, full))
        print(f"{'demo: fresh ' if self.fresh else ''}profile {self.learning.profile_path} session {self.learning.sessions}, "
              f"predictor {'on' if self.learning.predictor.enabled else 'off (river missing)'}; {self.learning.status()}", flush=True)
        tiers = ", ".join(f"{s}: " + " ".join(f"{t['notation']}(i{t['startup']})" for t in punishers[s]) for s in ("standing", "crouching"))
        menu = ", ".join(f"{c} {len(options['classes'][c])}" for c in CLASSES)
        print(f"bot P{bot + 1} {character} at difficulty {self.difficulty.level} "
              f"(reaction {self.difficulty.reaction_delay_frames}f, frame-perfect {self.difficulty.frame_perfect_chance:.0%}, "
              f"accuracy {self.difficulty.punish_accuracy:.0%}, execution error {self.difficulty.execution_error:.0%}, "
              f"movement {self.difficulty.movement_set}, temperature {self.difficulty.mixup_temperature}), "
              f"latency {latency}f; punishers from {source}: {tiers}; wakeups from {wake_source}; "
              f"options from {option_source}: {menu}. Kill key {self.config['kill_key']}.", flush=True)
        print(describe_combos(short, full, self.difficulty), flush=True)

    def poll(self):
        self.pad.check_kill()

    def frame(self, state, events):
        live = self.reflex.live(state)
        with trace.span("reflex"):
            records = self.reflex.step(state, events)
            records += self.combos.step(state, live)
        with trace.span("tactical"):
            decisions = self.detector.step(state, events)
            records += decisions
            learned = self.learning.step(state, events + decisions)
            records += learned
            if not self.combos.busy():
                records += self.tactical.step(state, events, self.reflex)
        self.report(learned)
        with trace.span("input"):
            bot = state["players"][1 - state["human_slot"]]
            self.seq.on_frame(state["frame"], bot, live)
            self.seq.pop_finished()
        return records

    def report(self, learned):
        for rec in learned:
            if rec.get("t") == "round_summary":
                print(f"learning r{rec['round']}: {self.learning.status()}", flush=True)

    def finish(self, state, events):
        if self.learning is None:
            return []
        learned = self.learning.step(state, events)
        self.report(learned)
        return learned

    def close(self):
        if self.seq is not None:
            self.seq.cancel()
        self.pad.release_all()


def resolve_player(args, root=None):
    if args.player:
        return args.player
    if args.demo:
        return DEMO_PLAYER
    return api.load_config(root)["player"]


def parse_args(argv=None, root=None):
    parser = argparse.ArgumentParser(description="Kumite bot: reflex layer (block, punish, throw break, wakeup) and neutral play on the virtual 2P pad, recording the session")
    add_session_args(parser, player_required=False)
    parser.set_defaults(difficulty=None)
    parser.add_argument("--demo", action="store_true", help="start from a fresh profile (player guest unless --player is given)")
    parser.add_argument("--loop", action="store_true", help="after a match ends, wait for the next match's round 1 and start a new session with the current config")
    parser.add_argument("--no-api", action="store_true", help="do not serve the brain API on :8765")
    parser.add_argument("--host", default=api.HOST, help="address the brain API listens on, e.g. this laptop's Tailscale IP for remote clients")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--timing", action="store_true", help="time every frame iteration and print count, p50, p95 and max at session end")
    args = parser.parse_args(argv)
    args.player_flag = args.player
    args.player = resolve_player(args, root)
    return args


def cli_patch(args):
    patch = {}
    if args.difficulty is not None:
        patch["difficulty"] = args.difficulty
    if args.player_flag:
        patch["player"] = args.player_flag
    return patch


def apply_cli(args, root=None):
    patch = cli_patch(args)
    if not patch:
        return api.load_config(root), []
    return api.update_config(patch, root)


def settings(args, root=None):
    cfg = api.load_config(root)
    difficulty = Difficulty.preset(cfg["difficulty"], cfg.get("knobs"))
    fresh = bool(args.demo or cfg.get("demo_mode"))
    player = DEMO_PLAYER if fresh and not args.player_flag else cfg["player"]
    return cfg, difficulty, player, fresh


def describe(cfg, difficulty, player, fresh, root=None):
    knobs = cfg.get("knobs") or {}
    knob_text = " with knobs " + " ".join(f"{k}={v}" for k, v in sorted(knobs.items())) if knobs else ""
    return (f"config {(root or data_dir()) / 'config.json'}: difficulty {difficulty.level}{knob_text}, player {player}, "
            f"demo {'on' if fresh else 'off'}")


def main(argv=None):
    tracing = trace.init()
    args = parse_args(argv)
    print(tracing, flush=True)
    cfg, errors = apply_cli(args)
    for error in errors:
        print(f"warning: config.json not updated from the command line: {error}", flush=True)
    outlet = None
    if not args.no_api:
        if api.start(host=args.host) is None:
            print(f"warning: brain API not started on {args.host}:{api.PORT} (port in use or address not on this machine?); playing without it", flush=True)
        else:
            print(f"brain API on http://{args.host}:{api.PORT} (DATA_DIR {data_dir().resolve()}); coach at {replay_url()}/coach/round", flush=True)
            outlet = Outlet(api.publish)

    reader = Reader(args.offsets)
    pad = None
    try:
        if not run_gate(reader, args.offsets):
            return 1
        pad = connect_pad()
        pacer = Pacer()
        while True:
            cfg, difficulty, player, fresh = settings(args)
            args.difficulty = difficulty.level
            args.player = player
            print(describe(cfg, difficulty, player, fresh) + (" (--loop: re-read before every match)" if args.loop else ""), flush=True)
            reason = run_session(reader, args, BotHooks(pad, difficulty, args.seed, player=player, fresh=fresh), outlet)
            if not args.loop or reason != MATCH_OVER:
                return 0
            print("loop: waiting for the next match's round 1; POST /config now to change the next session (Ctrl+C to quit)", flush=True)
            wait_for_match(reader, pacer, pad.check_kill)
    except KillSwitch as e:
        print(f"stopped: {e}", flush=True)
        return 1
    except KeyboardInterrupt:
        print("stopped: Ctrl+C while waiting for the next match", flush=True)
        return 0
    finally:
        if pad is not None:
            pad.release_all()
        reader.close()


if __name__ == "__main__":
    sys.exit(main())
