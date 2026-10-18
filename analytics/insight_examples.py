import argparse
import copy
import json
import tempfile
from pathlib import Path

from analytics.insights import InsightRepository, public
from analytics.repository import ROOT

FIXTURES = Path(__file__).parent / 'fixtures' / 'insights'
PUBLIC_FIXTURES = FIXTURES / 'public'
REAL_ID = '2026-10-18T05-14-03_sahil_djin_vs_kaz'
SYNTHETIC_ID = '2026-10-17T13-05-00_synth_djin_vs_kaz'


def event(frame, kind='hit', round_=1, **fields):
    return {'t': 'event', 'session_id': 'insight-example', 'round': round_, 'frame': frame,
            'kind': kind, 'actor': 1, 'target': 0, **fields}


def round_end(number):
    return event(100, 'round_end', number, detail={'winner': 1})


def learning(number):
    return {'t': 'learning_round', 'session_id': 'insight-example', 'round': number,
            'prediction_accuracy': None, 'habits': {}}


def example(root, records, rounds=(1,), focus=None, invalid=False):
    for name in ('sessions', 'recordings', 'learning'):
        (root / name).mkdir(exist_ok=True)
    meta = {'session_id': 'insight-example', 'started_at': '2026-10-18T00:00:00Z',
            'player': 'synthetic-example', 'human_slot': 0, 'human_character': 'devil_jin',
            'bot_character': 'kazuya', 'difficulty': 3, 'rounds': [], 'mode': 'synthetic'}
    (root / 'sessions/insight-example.json').write_text(json.dumps(meta), encoding='utf-8', newline='\n')
    text = ''.join(json.dumps(row) + '\n' for row in records)
    (root / 'recordings/insight-example.jsonl').write_text(text + ('{invalid}\n' if invalid else ''), encoding='utf-8', newline='\n')
    (root / 'learning/insight-example.jsonl').write_text(''.join(json.dumps(learning(n)) + '\n' for n in rounds), encoding='utf-8', newline='\n')
    return InsightRepository(root).snapshot('insight-example', limit=5, focus=focus)


def build_examples():
    results = {
        'real': InsightRepository(ROOT / 'data/samples/live_learning').snapshot(REAL_ID, limit=5),
        'synthetic': InsightRepository(ROOT / 'data/samples/synthetic').snapshot(SYNTHETIC_ID, limit=5),
    }
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        lows = [event(n, hit_level='low', damage=10) for n in range(1, 7)]
        results['observed'] = example(root, lows + [round_end(1)])
        results['early_signal'] = example(root, lows[:3] + [round_end(1)])
        results['no_opportunities'] = example(root, [round_end(1)])
        results['invalid_recording'] = example(root, lows + [round_end(1)], invalid=True)
        results['orphan_break'] = example(root, [event(1, 'throw_break', actor=0, target=1), round_end(1)])
        throws = [event(20 + n, 'throw', damage=10) for n in range(3)]
        results['manual_focus'] = example(root, lows + throws + [round_end(1)], focus='throw_defense')
        two_rounds = lows + [round_end(1), event(1, round_=2, hit_level='low', damage=10), round_end(2)]
        results['pending_learning'] = example(root, two_rounds, rounds=(1,))
        results['current_learning'] = example(root, two_rounds, rounds=(1, 2))
        blocked = event(1, 'block', hit_level='low', frame_advantage=-12, move_id=42,
                        detail={'read_frame': 2, 'attacker_total': 14, 'attacker_frame': 1,
                                'defender_total': 2, 'defender_frame': 1, 'string_continued': False})
        base = json.loads((ROOT / 'contracts/examples/gamestate.json').read_text())
        recovery = []
        for frame in range(2, 16):
            state = copy.deepcopy(base)
            state.update(session_id='insight-example', round=1, frame=frame)
            state['players'][0]['frames_until_actionable'] = max(0, 3-frame)
            state['players'][1].update(move_id=42, frame_in_move=frame-1, hit_level='low', frames_until_actionable=15-frame)
            recovery.append(state)
        results['mixed_outcomes'] = example(root, [blocked, *recovery, round_end(1)])
    return results


def text(value):
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n'


def serialized_examples(examples=None):
    return {name + '.json': text(value) for name, value in (examples or build_examples()).items()}


def serialized_public(examples=None):
    return {name + '.json': text(public(value)) for name, value in (examples or build_examples()).items()}


def drift(directory, values):
    actual = {p.name for p in directory.glob('*.json')}
    return sorted(set(values) ^ actual | {name for name, value in values.items()
                                         if not (directory / name).exists() or (directory / name).read_text(encoding='utf-8') != value})


def main(argv=None):
    parser = argparse.ArgumentParser(description='Generate review-only insight fixtures from the production builder')
    parser.add_argument('--check', action='store_true', help='verify committed examples without rewriting them')
    args = parser.parse_args(argv)
    examples = build_examples()
    outputs = ((FIXTURES, serialized_examples(examples)), (PUBLIC_FIXTURES, serialized_public(examples)))
    if args.check:
        stale = [f'{directory.relative_to(FIXTURES.parent)}/{name}' for directory, values in outputs for name in drift(directory, values)]
        if stale:
            parser.exit(1, 'Insight fixture drift: ' + ', '.join(stale) + '\n')
        print(f'PASS: {len(examples)} internal and {len(examples)} public v1 insight examples match the builder')
        return
    for directory, values in outputs:
        directory.mkdir(parents=True, exist_ok=True)
        for name, content in values.items():
            (directory / name).write_text(content, encoding='utf-8', newline='\n')
    print(f'Wrote {len(examples)} internal and {len(examples)} public v1 fixtures under analytics/fixtures/insights')


if __name__ == '__main__':
    main()
