import json
import random
import re
import unittest
from pathlib import Path

from game.combos import ComboRunner, hit_limit, last_press, link_notation, listed_damage, load_routes, plan
from game.difficulty import Difficulty
from game.notation import compile_notation, describe
from game.sequencer import Sequencer
from game.tests.test_pad import fake_pad
from game.tests.test_sequencer import ScriptedRng

DATA = load_routes()
ROUTES = DATA["routes"]
PUNISHERS = DATA["punishers"]["standing"] + DATA["punishers"]["crouching"]
MOVES = json.loads((Path(__file__).resolve().parents[2] / "characters" / "kazuya" / "moves.json").read_text(encoding="utf-8"))["moves"]
BOT, TARGET = 1, 0


def player(health=180, free=True, until=0, move=0x8001, reaction=0, side=0):
    return {"health": health, "free_movement": free, "frames_until_actionable": until, "move_id": move,
            "hit_reaction": reaction, "side": side}


class Sim:
    def __init__(self, route="ewgf_reliable", difficulty=None, rng=None):
        self.pad, self.device = fake_pad()
        self.seq = Sequencer(self.pad, 2, difficulty=difficulty, rng=rng or random.Random(0))
        self.runner = ComboRunner(ROUTES[route], self.seq, BOT, name=route)
        self.frame = 99
        self.bot = player(side=1)
        self.target = player()

    def step(self, free=None, until=None, move=None):
        self.frame += 1
        if free is not None:
            self.bot["free_movement"] = free
        if until is not None:
            self.bot["frames_until_actionable"] = until
        if move is not None:
            self.bot["move_id"] = move
        players = [None, None]
        players[BOT], players[TARGET] = dict(self.bot), dict(self.target)
        out = self.runner.on_state({"frame": self.frame, "players": players})
        self.seq.on_frame(self.frame, players[BOT])
        return out

    def hit(self, damage, reaction=12, free=None, until=None, move=None):
        self.target["health"] -= damage
        self.target["hit_reaction"] = reaction
        return self.step(free, until, move)

    def busy_until(self, frame, move, until):
        outs = []
        while self.frame < frame:
            outs.append(self.step(free=False, until=until, move=move))
        return outs

    def connect(self, link_start, move=0x700):
        frames = self.runner.move.frames
        entry = link_start + last_press(frames) + self.seq.latency
        self.busy_until(entry - 1, move - 1, 40)
        self.step(free=False, until=40, move=move)
        return self.hit(10, free=False, until=30, move=move)


class NotationRoundTripTest(unittest.TestCase):
    def assertRoundTrip(self, text):
        frames = compile_notation(text)
        self.assertEqual(describe(frames), text)
        self.assertEqual(compile_notation(describe(frames)), frames)

    def test_every_route_link_and_hit_prefix(self):
        for name, route in ROUTES.items():
            for limit in (None, 1, 2, 3):
                for link in plan(route, limit):
                    with self.subTest(route=name, limit=limit, link=link.notation):
                        self.assertRoundTrip(link.notation)
            for seg in route["segments"]:
                for hit in seg["hits"]:
                    with self.subTest(route=name, hit=hit["command"]):
                        self.assertRoundTrip(link_notation(seg.get("lead"), hit["command"]))

    def test_every_punisher(self):
        for p in PUNISHERS:
            with self.subTest(punisher=p["command"]):
                self.assertRoundTrip(p["command"])
                self.assertEqual(p["hits"][-1]["command"], p["command"])
                for hit in p["hits"]:
                    self.assertRoundTrip(hit["command"])

    def test_hit_commands_are_string_prefixes(self):
        for name, route in ROUTES.items():
            for seg in route["segments"]:
                commands = [h["command"] for h in seg["hits"]]
                for a, b in zip(commands, commands[1:]):
                    with self.subTest(route=name, hit=b):
                        self.assertTrue(b.startswith(a + ","), (a, b))


class RouteDataTest(unittest.TestCase):
    def moves_entry(self, hit):
        if hit["move_id"]:
            for m in MOVES:
                if hit["move_id"] in m["move_ids"]:
                    return m
        key = hit["command"].replace("ws+", "ws")
        return next((m for m in MOVES if m["command"] == key), None)

    def test_listed_damage_is_sum_of_hits(self):
        for name, route in ROUTES.items():
            with self.subTest(route=name):
                self.assertEqual(route["listed_damage"], listed_damage(plan(route)))
        for p in PUNISHERS:
            with self.subTest(punisher=p["command"]):
                self.assertEqual(p["listed_damage"], sum(h["damage"] for h in p["hits"]))

    def test_damage_and_ids_match_moves_json(self):
        hits = [h for r in ROUTES.values() for s in r["segments"] for h in s["hits"]] + [h for p in PUNISHERS for h in p["hits"]]
        for hit in hits:
            entry = self.moves_entry(hit)
            if entry is None:
                continue
            with self.subTest(hit=hit["command"], move_id=hit["move_id"]):
                listed = [int(n) for n in re.findall(r"\d+", entry["damage"])]
                self.assertIn(hit["damage"], listed)

    def test_tornado_once_per_route(self):
        for name, route in ROUTES.items():
            with self.subTest(route=name):
                self.assertEqual(sum(1 for s in route["segments"] for h in s["hits"] if h.get("tornado")), 1)


class DifficultyCutTest(unittest.TestCase):
    def test_limits(self):
        self.assertEqual(hit_limit(Difficulty.preset(1)), 2)
        self.assertEqual(hit_limit(Difficulty.preset(2)), 2)
        for level in (3, 4, 5):
            self.assertIsNone(hit_limit(Difficulty.preset(level)))
        self.assertIsNone(hit_limit(None))

    def test_short_plans(self):
        expected = {"ewgf_reliable": ["f,n,d,df+2", "f,F,b+2"], "ff3": ["f,F+3", "f,n,d,df+1+2"], "ch_df2": ["df+2", "f,n,d,df+2"]}
        for name, notations in expected.items():
            with self.subTest(route=name):
                links = plan(ROUTES[name], 2)
                self.assertEqual([link.notation for link in links], notations)
                self.assertEqual(sum(len(link.hits) for link in links), 2)

    def test_runner_cut_follows_sequencer_difficulty(self):
        pad, _ = fake_pad()
        for level, count in ((1, 2), (2, 2), (3, 4), (5, 4)):
            seq = Sequencer(pad, 2, difficulty=Difficulty.preset(level))
            runner = ComboRunner(ROUTES["ewgf_reliable"], seq, BOT)
            with self.subTest(level=level):
                self.assertEqual(len(runner.links), count)
                self.assertEqual(runner.links[-1].notation, "f,F,b+2" if level <= 2 else "b+2,2,1+2")

    def test_full_plan_notations(self):
        self.assertEqual([link.notation for link in plan(ROUTES["ewgf_reliable"])],
                         ["f,n,d,df+2", "f,F,b+2,2", "df+1,df+2", "b+2,2,1+2"])
        self.assertEqual([link.notation for link in plan(ROUTES["ff3"])],
                         ["f,F+3", "f,n,d,df+1+2", "1,2,4,3", "f,F,b+2,2,1+2"])
        self.assertEqual([link.notation for link in plan(ROUTES["ch_df2"])],
                         ["df+2", "f,n,d,df+2", "f,F,b+2,2", "df+1,df+2", "b+2,2,1+2"])


class RunnerTimingTest(unittest.TestCase):
    def test_first_link_when_free(self):
        sim = Sim()
        self.assertEqual(sim.step(), "f,n,d,df+2")
        self.assertEqual(sim.runner.move.start_frame, 100)
        self.assertEqual(sim.device.pressed, {"DPAD_LEFT"})

    def test_first_link_waits_for_actionable(self):
        sim = Sim()
        outs = [sim.step(free=False, until=u, move=0x600) for u in (9, 8, 7, 6)]
        self.assertEqual(outs, [None] * 4)
        self.assertEqual(sim.step(free=False, until=5, move=0x600), "f,n,d,df+2")

    def test_next_link_needs_connect_then_free_for_dash(self):
        sim = Sim()
        sim.step()
        self.assertIsNone(sim.connect(100, 0x701))
        self.assertEqual(sim.runner.index, 1)
        for until in range(29, 0, -1):
            self.assertIsNone(sim.step(free=False, until=until, move=0x701))
        self.assertEqual(sim.step(free=True, until=0, move=0x8001), "f,F,b+2,2")
        self.assertEqual(sim.runner.submitted[-1]["frame"], sim.frame)

    def test_no_next_link_without_connect(self):
        sim = Sim()
        sim.step()
        outs = sim.busy_until(140, 0x701, 3)
        self.assertEqual(outs, [None] * len(outs))
        self.assertEqual(sim.runner.index, 0)
        self.assertIsNone(sim.step(free=True, until=0, move=0x8001))
        self.assertEqual(sim.runner.status, "dropped")
        self.assertEqual(len(sim.runner.submitted), 1)

    def test_prepress_link_starts_at_latency(self):
        sim = Sim()
        sim.step()
        sim.connect(100, 0x701)
        sim.busy_until(sim.frame + 5, 0x701, 1)
        start = sim.frame + 1
        self.assertEqual(sim.step(free=True, until=0, move=0x8001), "f,F,b+2,2")
        sim.connect(start, 0x690)
        outs = [sim.step(free=False, until=u, move=0x690) for u in (6, 5, 4, 3)]
        self.assertEqual(outs, [None] * 4)
        self.assertEqual(sim.step(free=False, until=2, move=0x690), "df+1,df+2")
        self.assertEqual(sim.device.pressed, {"DPAD_DOWN", "DPAD_LEFT", "X"})

    def test_early_string_hit_is_not_the_final_hit(self):
        sim = Sim()
        sim.step()
        sim.connect(100, 0x701)
        start = sim.frame + 1
        self.assertEqual(sim.step(free=True, until=0, move=0x8001), "f,F,b+2,2")
        press = start + last_press(sim.runner.move.frames)
        sim.busy_until(press - 1, 0x6F4, 40)
        sim.step(free=False, until=40, move=0x685)
        sim.busy_until(press + 6, 0x685, 30)
        sim.hit(12, free=False, until=30, move=0x685)
        self.assertEqual(sim.runner.index, 1)
        self.assertFalse(sim.runner.hits[-1]["final"])
        sim.busy_until(sim.frame + 8, 0x685, 25)
        sim.step(free=False, until=30, move=0x686)
        self.assertEqual(sim.runner.index, 1)
        sim.hit(14, free=False, until=28, move=0x686)
        self.assertTrue(sim.runner.hits[-1]["final"])
        self.assertEqual(sim.runner.index, 2)

    def test_full_route_done_and_damage(self):
        sim = Sim()
        for move in (0x701, 0x690, 0x6A7, 0x687):
            outs = [sim.step(free=True, until=0, move=0x8001) for _ in range(3)]
            self.assertEqual(sum(o is not None for o in outs), 1)
            start = sim.frame - 2 + next(i for i, o in enumerate(outs) if o is not None)
            sim.connect(start, move)
        self.assertEqual(sim.runner.status, "done")
        self.assertEqual(len(sim.runner.submitted), 4)
        self.assertEqual(sim.runner.damage, 40)
        self.assertEqual(sim.runner.listed_damage, 126)
        self.assertEqual(sim.runner.first_reaction, 12)
        self.assertIsNone(sim.step())

    def test_counter_reset_aborts_and_releases(self):
        sim = Sim()
        sim.step()
        sim.frame = 10
        sim.step()
        self.assertEqual(sim.runner.status, "aborted")
        self.assertEqual(sim.device.pressed, set())
        self.assertFalse(sim.seq.busy())

    def test_bot_hit_interrupts(self):
        sim = Sim()
        sim.step()
        sim.bot["health"] -= 10
        self.assertIsNone(sim.step(free=False, until=20, move=0x600))
        self.assertEqual(sim.runner.status, "interrupted")
        self.assertFalse(sim.seq.busy())


class ExecutionErrorTest(unittest.TestCase):
    def test_errors_come_from_sequencer_difficulty(self):
        sim = Sim(difficulty=Difficulty.preset(3).with_knobs(execution_error=1.0), rng=random.Random(3))
        sim.step()
        self.assertEqual(len(sim.runner.errors), 1)
        self.assertEqual(sim.runner.errors[0][0], 0)
        self.assertNotEqual(sim.runner.move.frames, compile_notation("f,n,d,df+2"))

    def test_no_errors_at_level_5(self):
        sim = Sim(difficulty=Difficulty.preset(5))
        sim.step()
        self.assertEqual(sim.runner.errors, [])
        self.assertEqual(sim.runner.move.frames, compile_notation("f,n,d,df+2"))

    def test_connect_waits_for_delayed_last_press(self):
        sim = Sim(difficulty=Difficulty.preset(3).with_knobs(execution_error=1.0), rng=ScriptedRng([0.0, 0.0], 3, 2))
        sim.step()
        self.assertEqual(sim.runner.errors, [(0, "delayed input 3 by 2")])
        self.assertEqual(last_press(sim.runner.move.frames), 5)
        sim.busy_until(104, 0x6F7, 40)
        sim.step(free=False, until=40, move=0x701)
        sim.hit(5, free=False, until=40, move=0x701)
        self.assertEqual(sim.runner.index, 0)
        sim.step(free=False, until=40, move=0x702)
        sim.hit(5, free=False, until=40, move=0x702)
        self.assertEqual(sim.runner.index, 1)


if __name__ == "__main__":
    unittest.main()
