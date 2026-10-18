import copy
import json
import os
import random
import time
import unittest
from unittest.mock import patch

os.environ['SENTRY_DSN'] = ''

from analytics import repository
from analytics.fastcheck import compile_schema
from analytics.repository import FAST_RECORDS, RECORD_SCHEMAS, ROOT, SCHEMAS, VALIDATORS, DataError, TailReader, checked_record

SID = '2026-10-18T05-14-03_sahil_djin_vs_kaz'
RECORDING = ROOT / 'data/samples/live_learning/recordings' / f'{SID}.jsonl'
REPLACEMENTS = [None, True, False, 0, 1, -1, 2, 1.5, 2.0, 1e9, -1e9, '', 'x', 'neutral', [], [1], {}, {'a': 1}]


def locations(value, prefix=()):
    yield prefix
    if isinstance(value, dict):
        for key, child in value.items():
            yield from locations(child, prefix + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from locations(child, prefix + (index,))


def mutate(record, rng):
    clone = copy.deepcopy(record)
    path = rng.choice([p for p in locations(clone) if p])
    parent = clone
    for step in path[:-1]:
        parent = parent[step]
    if rng.random() < 0.3:
        if isinstance(parent, dict):
            del parent[path[-1]]
        else:
            parent.pop(path[-1])
    else:
        parent[path[-1]] = copy.deepcopy(rng.choice(REPLACEMENTS))
    return clone


def samples():
    chosen, seen = {'state': [], 'event': [], 'round_summary': []}, set()
    with RECORDING.open() as stream:
        for line in stream:
            record = json.loads(line)
            kind = record['t']
            if kind == 'state' and len(chosen['state']) < 4 and record['frame'] % 500 == 0:
                chosen['state'].append(record)
            elif kind == 'event' and record['kind'] not in seen:
                seen.add(record['kind'])
                chosen['event'].append(record)
            elif kind == 'round_summary':
                chosen['round_summary'].append(record)
    return chosen


class CompiledValidatorTest(unittest.TestCase):
    def test_hot_record_schemas_compile(self):
        for kind in ('state', 'event', 'round_summary'):
            self.assertIsNotNone(FAST_RECORDS[kind], kind)

    def test_agrees_with_jsonschema_on_mutated_real_records(self):
        rng = random.Random(20261018)
        chosen = samples()
        for kind, records in chosen.items():
            validator = VALIDATORS[RECORD_SCHEMAS[kind]]
            fast = FAST_RECORDS[kind]
            self.assertTrue(records, kind)
            invalid = total = 0
            for record in records:
                self.assertTrue(validator.is_valid(record))
                self.assertTrue(fast(record))
                for _ in range(400):
                    changed = mutate(record, rng)
                    expected = validator.is_valid(changed)
                    self.assertEqual(fast(changed), expected, (kind, changed))
                    total += 1
                    invalid += not expected
            self.assertGreater(invalid / total, 0.2, kind)

    def test_booleans_are_not_integers_or_enum_members(self):
        check = compile_schema({'type': 'object', 'properties': {'slot': {'type': 'integer', 'enum': [0, 1]}, 'n': {'type': 'number'}}})
        self.assertTrue(check({'slot': 1, 'n': 2.5}))
        self.assertTrue(check({'slot': 1.0}))
        self.assertFalse(check({'slot': True}))
        self.assertFalse(check({'n': False}))

    def test_unsupported_keywords_fall_back_to_jsonschema(self):
        self.assertIsNone(compile_schema({'type': 'object', 'additionalProperties': False}))
        self.assertIsNone(compile_schema({'type': 'string', 'format': 'date-time'}))
        self.assertIsNone(compile_schema({'$ref': '#/$defs/missing'}))

    def test_invalid_state_still_raises_the_jsonschema_diagnostic(self):
        record = next(r for r in samples()['state'])
        record['players'][0]['health'] = 'full'
        with self.assertRaisesRegex(DataError, 'invalid data at players/0/health'):
            checked_record(record, SID, 'recording')
        with patch.dict(FAST_RECORDS, {'state': None}):
            with self.assertRaisesRegex(DataError, 'invalid data at players/0/health'):
                checked_record(record, SID, 'recording')

    def test_every_contract_schema_used_for_records_is_unchanged_by_the_fast_path(self):
        for kind, name in RECORD_SCHEMAS.items():
            self.assertIn(name, SCHEMAS)
            self.assertIn(name, VALIDATORS)


class ColdLoadBudgetTest(unittest.TestCase):
    def test_live_sample_parses_inside_the_budget(self):
        tail = TailReader(RECORDING, SID)
        started = time.perf_counter()
        tail.refresh()
        elapsed = time.perf_counter() - started
        self.assertEqual(tail.skipped, 0)
        self.assertGreater(len(tail.records), 10000)
        self.assertLess(elapsed, 2.0)
