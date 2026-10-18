import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from analytics.repository import FileRepository, incomplete_json
from analytics import stats

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = {path.name.removesuffix('.schema.json'): json.loads(path.read_text()) for path in (ROOT / 'contracts').glob('*.schema.json')}
VALIDATORS = {name: Draft202012Validator(schema, format_checker=FormatChecker()) for name, schema in SCHEMAS.items()}
VALIDATORS['learning_round'] = Draft202012Validator({**SCHEMAS['metrics']['$defs']['round'], '$defs': SCHEMAS['metrics']['$defs']})
KINDS = {'state': 'gamestate', 'event': 'event', 'round_summary': 'round_summary', 'learning_round': 'learning_round', 'plan': 'gameplan'}
TABLES = {'state': 'frames', 'event': 'events', 'round_summary': 'round_metrics', 'learning_round': 'round_metrics'}


class InputError(Exception):
    pass


def invalid_constant(value):
    raise ValueError('non-finite number')


def loads(text):
    return json.loads(text, parse_constant=invalid_constant)


def checked(record, name, label):
    error = next(VALIDATORS[name].iter_errors(record), None)
    if error:
        raise InputError(f'{label}: invalid {name} record ({error.validator})')


def text_file(path):
    try:
        before = path.stat()
        text = path.read_text(encoding='utf-8')
        after = path.stat()
        if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
            raise InputError(f'{path.name}: changed while reading; retry')
        return text
    except (OSError, UnicodeError) as exc:
        raise InputError(f'{path.name}: cannot read file') from exc


def metadata(path):
    try:
        meta = loads(text_file(path))
    except ValueError as exc:
        raise InputError(f'{path.name}: invalid JSON') from exc
    checked(meta, 'session', path.name)
    sid = meta['session_id']
    if not sid or sid in ('.', '..') or '/' in sid or '\\' in sid:
        raise InputError(f'{path.name}: unsafe session id')
    try:
        moment = datetime.fromisoformat(meta['started_at'].replace('Z', '+00:00'))
        if moment.tzinfo is None:
            raise ValueError('timezone required')
    except ValueError as exc:
        raise InputError(f'{path.name}: invalid start timestamp') from exc
    return meta


def records(path, sid, source):
    text = text_file(path)
    lines = text.splitlines()
    result = []
    for index, line in enumerate(lines, 1):
        if not line.strip():
            continue
        label = f'{path.name}:{index}'
        try:
            record = loads(line)
        except json.JSONDecodeError as exc:
            if index == len(lines) and not text.endswith('\n') and incomplete_json(line, exc):
                break
            raise InputError(f'{label}: malformed JSON') from exc
        except ValueError as exc:
            raise InputError(f'{label}: malformed JSON') from exc
        if not isinstance(record, dict):
            raise InputError(f'{label}: expected object')
        kind = record.get('t')
        if not isinstance(kind, str) or kind not in KINDS:
            continue
        body = {key: value for key, value in record.items() if key not in ('t', 'frame', 'round', 'session_id')} if kind == 'plan' else record
        checked(body, KINDS[kind], label)
        if record.get('session_id', sid) != sid:
            raise InputError(f'{label}: session id mismatch')
        if kind == 'plan':
            continue
        if kind != 'learning_round' and 'frame' in record and (type(record['frame']) is not int or record['frame'] < 0):
            raise InputError(f'{label}: invalid frame')
        result.append((source, index, record))
    return result


@dataclass(frozen=True)
class Row:
    observed_at: datetime
    source: str
    source_line: int
    record: dict


@dataclass(frozen=True)
class RoundBatch:
    meta: dict
    number: int
    fingerprint: str
    rows: dict


def discover(data_dir, errors=None):
    repository = FileRepository(data_dir)
    found = {sid: (entry[2], entry[3]) for sid, entry in repository._sessions().items()}
    if errors is not None:
        errors.update(repository.invalid_sessions)
    return found


def prepare(meta, recording, data_dir):
    sid = meta['session_id']
    items = records(recording, sid, 'recording')
    learning = Path(data_dir) / 'learning' / f'{sid}.jsonl'
    if learning.exists():
        items += [item for item in records(learning, sid, 'learning') if item[2]['t'] == 'learning_round']
    grouped = {}
    for item in items:
        grouped.setdefault(item[2]['round'], []).append(item)
    start = datetime.fromisoformat(meta['started_at'].replace('Z', '+00:00'))
    offset = 0
    batches = []
    for number, group in sorted(grouped.items()):
        framed = [record['frame'] for source, line, record in group if source == 'recording' and 'frame' in record]
        first, last = (min(framed), max(framed)) if framed else (0, 0)
        closed = any(record['t'] == 'round_summary' or (record['t'] == 'event' and record['kind'] == 'round_end') for source, line, record in group if source == 'recording')
        if not closed:
            break
        rows = {name: [] for name in ('frames', 'events', 'round_metrics')}
        for source, line, record in group:
            frame = record.get('frame', last) if record['t'] != 'learning_round' else last
            try:
                observed_at = start + timedelta(microseconds=round((offset + frame - first) * 1_000_000 / 60))
            except (OverflowError, ValueError) as exc:
                raise InputError(f'{sid}: round {number} has out-of-range frame timing') from exc
            rows[TABLES[record['t']]].append(Row(observed_at, source, line, record))
        from analytics.stats import compute

        recorded = [record for source, line, record in group if source == 'recording']
        calculated = compute(sid, meta, recorded)['rounds'][0]
        moment = max(row.observed_at for values in rows.values() for row in values)
        rows['round_metrics'].append(Row(moment, 'calculated', 0, {'t': 'calculated_round', 'session_id': sid, **calculated}))
        content = {'version': stats.CALCULATION_VERSION, 'meta': meta, 'round': number, 'offset': offset, 'records': group}
        digest = hashlib.sha256(json.dumps(content, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()).hexdigest()
        batches.append(RoundBatch(meta, number, digest, rows))
        offset += last - first + 1
    return batches
