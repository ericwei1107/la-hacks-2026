import random
import unittest
from pathlib import Path

from game.bot import BotHooks
from game.comboplay import NONE, ROUND_OVER, ComboPlay, describe, full_ids, landed, load_play_routes, short_ids
from game.combos import last_press
from game.difficulty import Difficulty
from game.sequencer import Sequencer
from game.summarize import load_jsonl
from game.tests.test_pad import fake_pad

ROUTES = load_play_routes("kazuya")
SHORT, FULL = ROUTES
HUMAN, BOT = 0, 1
LATENCY = 2
VERSUS = Path(__file__).resolve().parents[2] / "data" / "samples" / "versus_djin_vs_kaz_l3.zip"


def player(**values):
    p = {"health": 180, "free_movement": True, "frames_until_actionable": 0, "move_id": 0x8001, "frame_in_move": 1,
         "hit_reaction": 0, "hit_level": "none", "side": 0, "x": 0, "z": 0, "heat_active": False}
    p.update(values)
    return p


class FixedRng(random.Random):
    def __init__(self, value):
        super().__init__(0)
        self.value = value

    def random(self):
        return self.value


class Sim:
    def __init__(self, level=5, rng=None):
        self.pad, self.device = fake_pad()
        self.difficulty = Difficulty.preset(level).with_knobs(execution_error=0.0)
        self.rng = rng or random.Random(0)
        self.seq = Sequencer(self.pad, LATENCY, self.difficulty, self.rng)
        self.play = ComboPlay(self.seq, self.difficulty, self.rng, ROUTES)
        self.frame = 99
        self.human = player()
        self.bot = player(side=1, x=900)
        self.records = []

    def step(self, live=True, **bot):
        self.frame += 1
        in_move = bot.pop("frame_in_move", None)
        changed = bot.get("move_id", self.bot["move_id"]) != self.bot["move_id"]
        self.bot.update(bot)
        self.bot["frame_in_move"] = in_move if in_move is not None else 1 if changed else self.bot["frame_in_move"] + 1
        players = [dict(self.human), dict(self.bot)]
        state = {"t": "state", "session_id": "s", "round": 1, "frame": self.frame, "human_slot": HUMAN, "players": players}
        recs = self.play.step(state, live)
        self.seq.on_frame(self.frame, players[BOT], live)
        self.seq.pop_finished()
        self.records += recs
        return recs

    def hit(self, damage, reaction=3, **bot):
        self.human.update(health=self.human["health"] - damage, hit_reaction=reaction, free_movement=False)
        return self.step(**bot)

    def land(self, move_id, damage=20, reaction=12, **bot):
        self.step(free_movement=False, move_id=move_id, frame_in_move=10, frames_until_actionable=40, hit_level="high")
        return self.hit(damage, reaction, free_movement=False, frames_until_actionable=39, **bot)

    def busy(self, frames, move_id):
        for _ in range(frames):
            self.step(free_movement=False, frames_until_actionable=20, move_id=move_id)

    def connect_link(self, move_id, damage=10):
        runner = self.play.runner
        index = runner.index
        while runner.move is None or runner.move.start_frame is None:
            self.step(free_movement=True, frames_until_actionable=0, move_id=0x8001)
        entry = runner.move.start_frame + last_press(runner.move.frames) + LATENCY
        while self.frame < entry - 1:
            self.step(free_movement=False, frames_until_actionable=40, move_id=0x6F4)
        self.step(free_movement=False, frames_until_actionable=40, move_id=move_id)
        need = sum(1 for h in runner.links[index].hits if not h.get("optional"))
        for _ in range(need):
            self.hit(damage, free_movement=False, frames_until_actionable=30, move_id=move_id)

    def combo_records(self):
        return [r for r in self.records if r["reflex"]["kind"] == "combo"]


class RouteTableTest(unittest.TestCase):
    def test_kazuya_routes(self):
        self.assertEqual(sorted(SHORT), ["ewgf_reliable", "ff3"])
        self.assertEqual(sorted(FULL), sorted(f"demo{i}" for i in range(1, 11)))
        self.assertEqual(load_play_routes("devil_jin"), ({}, {}))

    def test_launcher_ids(self):
        self.assertEqual(short_ids(SHORT["ewgf_reliable"]), {0x701, 0x702})
        self.assertEqual(short_ids(SHORT["ff3"]), set())
        self.assertIn(0x702, full_ids(FULL["demo4"]))
        self.assertNotIn(0x701, full_ids(FULL["demo4"]))
        self.assertIn(0x696, full_ids(FULL["demo3"]))
        self.assertIn(0x6AF, full_ids(FULL["demo2"]))
        self.assertIn(0x6FA, full_ids(FULL["demo10"]))

    def test_describe(self):
        text = describe(SHORT, FULL, Difficulty.preset(1))
        self.assertIn("short: full route 0%", text)
        self.assertIn("short ff3 ewgf_reliable", text)
        self.assertIn("full demo1 demo2", text)
        self.assertIn("optimal: full route 100%", describe(SHORT, FULL, Difficulty.preset(5)))

    def test_block_is_not_a_landed_hit(self):
        self.assertFalse(landed(player(), player(hit_reaction=1)))
        self.assertFalse(landed(player(), player(hit_reaction=2, health=170)))
        self.assertTrue(landed(player(), player(hit_reaction=12)))
        self.assertTrue(landed(player(hit_reaction=3), player(hit_reaction=3, health=170)))


class ChoiceTest(unittest.TestCase):
    def candidates(self, level, move_id, counter_hit=False, heat=False, rng=None):
        play = Sim(level, rng).play
        short, full = play.candidates(move_id, counter_hit, heat)
        return play.choose(short, full), short, full

    def test_low_difficulty_runs_the_short_route(self):
        for level in (1, 2):
            for move_id in (0x701, 0x702):
                with self.subTest(level=level, move_id=move_id):
                    (chosen, probs), _, _ = self.candidates(level, move_id)
                    self.assertEqual(chosen, "ewgf_reliable")
                    self.assertEqual(probs["ewgf_reliable"], 1.0)

    def test_high_difficulty_runs_the_best_full_route(self):
        for level in (4, 5):
            with self.subTest(level=level):
                (chosen, probs), short, full = self.candidates(level, 0x702)
                self.assertEqual(full, ["demo4", "demo8"])
                self.assertEqual(chosen, "demo4")
                self.assertEqual(probs, {"demo4": 1.0, "demo8": 0.0, "ewgf_reliable": 0.0, NONE: 0.0})

    def test_electric_ewgf_has_only_the_short_route(self):
        (chosen, _), short, full = self.candidates(5, 0x701)
        self.assertEqual((chosen, short, full), ("ewgf_reliable", ["ewgf_reliable"], []))

    def test_ws12_full_route_or_none(self):
        (chosen, _), _, full = self.candidates(5, 0x696)
        self.assertEqual((chosen, full), ("demo3", ["demo3", "demo7"]))
        (chosen, probs), _, _ = self.candidates(1, 0x696)
        self.assertEqual(chosen, NONE)
        self.assertEqual(probs[NONE], 1.0)

    def test_level_3_mixes_full_and_short(self):
        (chosen, probs), _, _ = self.candidates(3, 0x702, rng=FixedRng(0.3))
        self.assertEqual((chosen, probs["demo4"], probs["ewgf_reliable"]), ("demo4", 0.5, 0.5))
        (chosen, _), _, _ = self.candidates(3, 0x702, rng=FixedRng(0.7))
        self.assertEqual(chosen, "ewgf_reliable")
        (chosen, _), _, _ = self.candidates(3, 0x696, rng=FixedRng(0.7))
        self.assertEqual(chosen, NONE)

    def test_counter_hit_routes_need_a_counter_hit(self):
        _, short, full = self.candidates(5, 0x6AF)
        self.assertEqual((short, full), ([], []))
        (chosen, _), _, full = self.candidates(5, 0x6AF, counter_hit=True)
        self.assertEqual((chosen, full), ("demo2", ["demo2", "demo6"]))

    def test_heat_routes_need_heat(self):
        self.assertEqual(self.candidates(5, 0x6FA)[2], [])
        self.assertEqual(self.candidates(5, 0x6FA, heat=True)[2], ["demo10"])


class FollowTest(unittest.TestCase):
    def test_short_route_after_a_launch_punish(self):
        sim = Sim(1)
        sim.seq.submit("f,n,d,df+2", prepress=True, frame=sim.frame, reflex="punish")
        sim.step(free_movement=True)
        self.assertEqual(sim.land(0x701, damage=23), [])
        self.assertTrue(sim.play.busy())
        runner = sim.play.runner
        self.assertEqual((runner.index, len(runner.links)), (1, 3))
        sim.busy(10, 0x701)
        sim.connect_link(0x686)
        sim.connect_link(0x6AA)
        self.assertFalse(sim.play.busy())
        rec, = sim.combo_records()
        r = rec["reflex"]
        self.assertEqual((rec["t"], rec["source"], rec["chosen"]), ("tactical", "reflex", "ewgf_reliable"))
        self.assertEqual(rec["frame_asked"], r["start_frame"])
        self.assertEqual((r["route_set"], r["launcher"], r["launcher_move_id"], r["trigger"]),
                         ("short", "f,n,d,df+2", 0x701, "punish"))
        self.assertEqual((r["links_completed"], r["links_planned"], r["hits"], r["hits_planned"]), (3, 3, 5, 5))
        self.assertEqual((r["dropped"], r["status"], r["damage"]), (False, "done", 63))
        self.assertEqual(r["end_frame"], rec["frame"])

    def test_drop_when_the_hit_reaction_is_lost(self):
        sim = Sim(5)
        sim.land(0x701, damage=23)
        sim.busy(10, 0x701)
        sim.step(free_movement=True, frames_until_actionable=0, move_id=0x8001)
        self.assertTrue(sim.seq.busy())
        sim.human.update(hit_reaction=0, free_movement=True)
        recs = sim.step(free_movement=False, move_id=0x6F4)
        rec, = recs
        r = rec["reflex"]
        self.assertEqual((r["status"], r["dropped"], r["links_completed"]), ("dropped", True, 1))
        self.assertEqual(r["reason"], "hit reaction lost before link 2")
        self.assertFalse(sim.play.busy())
        self.assertFalse(sim.seq.busy())
        self.assertEqual(sim.device.pressed, set())

    def test_round_end_is_not_a_drop(self):
        sim = Sim(5)
        sim.land(0x701, damage=23)
        sim.human.update(health=0)
        rec, = sim.step(live=False, move_id=0x701)
        r = rec["reflex"]
        self.assertEqual((r["status"], r["reason"], r["dropped"]), ("aborted", ROUND_OVER, False))

    def test_no_route_records_none_once_per_launcher(self):
        sim = Sim(1)
        rec, = sim.land(0x696, damage=10)
        self.assertEqual(rec["chosen"], NONE)
        self.assertEqual(rec["reflex"]["status"], NONE)
        self.assertIn("no short route", rec["reflex"]["reason"])
        sim.hit(12, free_movement=False, move_id=0x696)
        self.assertEqual(len(sim.combo_records()), 1)
        self.assertFalse(sim.play.busy())

    def test_blocked_launcher_starts_nothing(self):
        sim = Sim(5)
        self.assertEqual(sim.land(0x702, damage=0, reaction=1), [])
        self.assertFalse(sim.play.busy())

    def test_unrouted_launcher_starts_nothing(self):
        sim = Sim(5)
        self.assertEqual(sim.land(0x64B), [])
        self.assertFalse(sim.play.busy())

    def run_captured(self, name, move_id, diverge_at=None):
        route = FULL[name]
        sim = Sim(5)
        hits = route["hits"]
        sim.land(move_id, damage=hits[0][1])
        connect = sim.frame
        self.assertEqual(sim.play.runner.connect_frame, connect)
        replay = sim.seq.queue[0]
        self.assertEqual(replay.notation, f"captured:{name}")
        self.assertEqual(replay.earliest, connect + route["inputs"][0][0] - LATENCY)
        attacks = {a[0]: int(a[1], 16) for a in route["attacks"]}
        drops = {h[0]: h[1] for h in hits[1:]}
        for offset in range(1, hits[-1][0] + 1):
            if not sim.play.busy():
                break
            move = attacks.get(offset)
            if offset == diverge_at:
                move = 0x6C3
            if move is not None:
                sim.bot.update(move_id=move, frame_in_move=0, hit_level="mid")
            if offset in drops:
                sim.hit(drops[offset], free_movement=False, frames_until_actionable=30)
            else:
                sim.step(free_movement=False, frames_until_actionable=30)
        return sim

    def test_full_captured_route_done(self):
        sim = self.run_captured("demo4", 0x702)
        rec, = sim.combo_records()
        r = rec["reflex"]
        route = FULL["demo4"]
        self.assertEqual((rec["chosen"], r["route_set"], r["status"], r["dropped"]), ("demo4", "full", "done", False))
        self.assertEqual((r["links_completed"], r["links_planned"]), (len(route["hits"]), len(route["hits"])))
        self.assertEqual(r["damage"], route["damage"])
        self.assertEqual(r["connect_distance"], route["connect_distance"])
        self.assertEqual(r["distance"], 900)

    def test_ws12_launch_punish_runs_demo3(self):
        sim = self.run_captured("demo3", 0x696)
        rec, = sim.combo_records()
        self.assertEqual((rec["chosen"], rec["reflex"]["status"]), ("demo3", "done"))

    def test_captured_divergence_stops_and_returns_to_neutral(self):
        sim = self.run_captured("demo4", 0x702, diverge_at=26)
        rec, = sim.combo_records()
        r = rec["reflex"]
        self.assertEqual((r["status"], r["dropped"], r["links_completed"]), ("aborted", True, 1))
        self.assertTrue(r["reason"].startswith("diverged: move 0x06C3 at +26"))
        self.assertFalse(sim.seq.busy())
        self.assertEqual(sim.device.pressed, set())


class RecordedMatchTest(unittest.TestCase):
    def replay(self, level):
        pad, device = fake_pad()
        difficulty = Difficulty.preset(level)
        seq = Sequencer(pad, LATENCY, difficulty, random.Random(0))
        play = ComboPlay(seq, difficulty, random.Random(0), ROUTES)
        records = []
        for state in (r for r in load_jsonl(VERSUS) if r.get("t") == "state"):
            bot = state["players"][1 - state["human_slot"]]
            live = state["derived"]["situation"] != "round_over" and all(p["health"] > 0 for p in state["players"])
            records += play.step(state, live)
            seq.on_frame(state["frame"], bot, live)
            seq.pop_finished()
        return records, play

    @unittest.skipUnless(VERSUS.exists(), "sample recording missing")
    def test_recorded_ws1_punishes_start_demo3_at_level_5_and_none_at_level_1(self):
        high, play = self.replay(5)
        self.assertFalse(play.busy())
        self.assertGreaterEqual(len(high), 10)
        for rec in high:
            r = rec["reflex"]
            self.assertEqual((rec["chosen"], r["launcher_move_id"], r["route_set"]), ("demo3", 0x696, "full"))
            self.assertNotEqual(r["status"], "done")
        low, _ = self.replay(1)
        self.assertEqual(len(low), len(high))
        self.assertEqual({rec["chosen"] for rec in low}, {NONE})


class Recorder:
    def __init__(self, busy=False):
        self.calls = []
        self.is_busy = busy

    def step(self, *args):
        self.calls.append(args)
        return []

    def busy(self):
        return self.is_busy

    def live(self, state):
        return True


class BotHookTest(unittest.TestCase):
    def hooks(self, busy):
        pad, _ = fake_pad()
        hooks = BotHooks(pad, Difficulty.preset(5), config={"input_latency_frames": 2, "kill_key": "pause"})
        hooks.reflex, hooks.detector, hooks.learning = Recorder(), Recorder(), Recorder()
        hooks.tactical, hooks.combos = Recorder(), Recorder(busy)
        hooks.seq = Sequencer(pad, LATENCY)
        return hooks

    def test_tactical_waits_while_a_combo_runs(self):
        state = {"frame": 10, "human_slot": 0, "players": [player(), player(side=1)]}
        for busy in (False, True):
            with self.subTest(busy=busy):
                hooks = self.hooks(busy)
                hooks.frame(state, [])
                self.assertEqual(len(hooks.combos.calls), 1)
                self.assertEqual(len(hooks.tactical.calls), 0 if busy else 1)


if __name__ == "__main__":
    unittest.main()
