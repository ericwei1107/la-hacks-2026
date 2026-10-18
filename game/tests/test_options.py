import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from game.difficulty import Difficulty
from game.notation import compile_notation
from game.options import (ATTACK_CLASSES, BUCKETS, CLASSES, REQUIRED, allowed, default_plan, load_fallback, load_options, move_key,
                          move_name, normalize_table, step_direction)
from game.state import HIT_LEVELS

ROOT = Path(__file__).resolve().parents[2]
PLAN_V = Draft202012Validator(json.loads((ROOT / "contracts" / "gameplan.schema.json").read_text()))


def check_table(test, table):
    for cls in CLASSES:
        test.assertIn(cls, table["classes"])
        for e in table["classes"][cls]:
            compile_notation(e["notation"])
            test.assertTrue(set(e["ranges"]) <= set(BUCKETS), e)
            test.assertGreater(e["weight"], 0)
            if cls in ATTACK_CLASSES:
                test.assertIn(e["hit_level"], HIT_LEVELS, e)
            if cls == "throw":
                test.assertIn("break", e)
    for cls in REQUIRED:
        test.assertTrue(table["classes"][cls], cls)


class FallbackTest(unittest.TestCase):
    def test_table(self):
        table = normalize_table(load_fallback()["kazuya"])
        check_table(self, table)
        self.assertEqual({e["notation"] for e in table["classes"]["sidestep"]}, {"u", "d"})
        self.assertTrue(any("wavedash" in e["tags"] for e in table["classes"]["approach"]))
        self.assertTrue(all(e["hit_level"] in ("low", "special_low") for e in table["classes"]["low"]))
        self.assertTrue(any(e["hit_level"] == "low" for e in table["classes"]["low"]))
        self.assertEqual({e["break"] for e in table["classes"]["throw"]}, {"1/2", "1+2"})

    def test_move_names_and_keys(self):
        table = normalize_table(load_fallback()["kazuya"])
        self.assertEqual(move_name(table, 0x6A6), "df+1")
        self.assertEqual(move_name(table, 0x702), "f,n,d,df+2")
        self.assertIsNone(move_name(table, 0x1234))
        self.assertIsNone(move_name(table, None))
        self.assertEqual(move_key("df+1"), "df1")
        self.assertEqual(move_key("f,n,d,df+2"), "f_n_d_df2")
        self.assertEqual(move_key("1,1,2"), "1_1_2")
        self.assertEqual(move_key("ws+2"), "ws2")

    def test_default_plan_validates(self):
        self.assertEqual(list(PLAN_V.iter_errors(default_plan())), [])


class CharactersTest(unittest.TestCase):
    def test_repo_characters_preferred(self):
        table, source = load_options("kazuya")
        self.assertIn("characters/kazuya", source)
        check_table(self, table)
        for e in table["classes"]["mid"]:
            self.assertNotIn(e["hit_level"], ("low", "special_low", "throw"), e)
        self.assertIn("uf+1+2", {e["notation"] for e in table["classes"]["throw"]})
        self.assertIn("f,f", {e["notation"] for e in table["classes"]["approach"]})
        self.assertTrue(any("wavedash" in e["tags"] for e in table["classes"]["approach"]))
        self.assertEqual([e["notation"] for e in table["classes"]["wait"]], ["B"])
        self.assertEqual(move_name(table, 0x6A6), "df+1")
        self.assertTrue(any("homing" in e["tags"] for e in table["classes"]["mid"]))
        self.assertTrue(all("launcher" in e["tags"] for e in table["classes"]["launcher"]))

    def test_missing_characters_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            table, source = load_options("kazuya", root=tmp)
            self.assertIn("options_fallback.json", source)
            check_table(self, table)

    def test_broken_characters_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "characters" / "kazuya"
            folder.mkdir(parents=True)
            (folder / "options.json").write_text("{}")
            (folder / "moves.json").write_text("{}")
            table, source = load_options("kazuya", root=tmp)
            self.assertIn("options_fallback.json", source)
            check_table(self, table)
            (folder / "moves.json").write_text("not json")
            table, source = load_options("kazuya", root=tmp)
            self.assertIn("options_fallback.json", source)

    def test_unknown_character_uses_kazuya_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            table, source = load_options("shaheen", root=tmp)
            self.assertIn("no data for shaheen", source)
            check_table(self, table)


class GatingTest(unittest.TestCase):
    def test_movement_sets(self):
        wave = {"notation": "f,n,d,df,f,n,d,df", "movement_set": "character"}
        step = {"notation": "u", "movement_set": "sidestep"}
        dash = {"notation": "f,f", "movement_set": "basic"}
        for level, expect in ((1, (False, False, True)), (2, (False, True, True)), (3, (True, True, True)), (5, (True, True, True))):
            d = Difficulty.preset(level)
            self.assertEqual((allowed(wave, d), allowed(step, d), allowed(dash, d)), expect, level)

    def test_step_direction(self):
        self.assertEqual(step_direction("u", 0), "left")
        self.assertEqual(step_direction("d", 0), "right")
        self.assertEqual(step_direction("u", 1), "right")
        self.assertEqual(step_direction("d", 1), "left")
        self.assertIsNone(step_direction("b,b", 0))


if __name__ == "__main__":
    unittest.main()
