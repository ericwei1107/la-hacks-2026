import copy
import json
import hashlib
import logging
import re
import os
import threading
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from analytics.fastcheck import compile_schema
from analytics.observability import traced

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = {p.name.removesuffix('.schema.json'): json.loads(p.read_text()) for p in (ROOT / 'contracts').glob('*.schema.json')}
VALIDATORS = {name: Draft202012Validator(schema, format_checker=FormatChecker()) for name, schema in SCHEMAS.items()}
ROUND_VALIDATOR = Draft202012Validator({**SCHEMAS['metrics']['$defs']['round'], '$defs': SCHEMAS['metrics']['$defs']}, format_checker=FormatChecker())
EVAL_VALIDATOR = Draft202012Validator({'type': 'object', 'required': ['before', 'after'], 'properties': {key: {'type': ['number', 'null'], 'minimum': 0, 'maximum': 1} for key in ('before', 'after')}})
RECORD_SCHEMAS = {'state': 'gamestate', 'event': 'event', 'round_summary': 'round_summary', 'plan': 'gameplan', 'learning_round': 'metrics'}
FAST_RECORDS = {kind: compile_schema(SCHEMAS[RECORD_SCHEMAS[kind]]) for kind in ('state', 'event', 'round_summary')}
logger = logging.getLogger(__name__)


class DataError(Exception):
    pass


class Changed(Exception):
    pass


def validate(value, validator, label):
    error = next(validator.iter_errors(value), None)
    if error:
        location = '/'.join(str(part) for part in error.absolute_path) or 'root'
        raise DataError(f'{label}: invalid data at {location} ({error.validator})')


def safe_id(sid):
    return isinstance(sid, str) and bool(sid) and sid not in ('.', '..') and '/' not in sid and '\\' not in sid


def reject_constant(value):
    raise ValueError('non-finite JSON number')


def decode(text):
    return json.loads(text, parse_constant=reject_constant)


def incomplete_json(line, error):
    if not line.lstrip().startswith('{'):
        return False
    tail = line[error.pos:].strip()
    return (error.pos >= len(line.rstrip()) or error.msg.startswith('Unterminated string')
            or (bool(tail) and any(token.startswith(tail) for token in ('true', 'false', 'null')))
            or (error.msg.startswith('Invalid \\u') and re.search(r'\\u[0-9a-fA-F]{0,3}$', line) is not None)
            or (error.msg.startswith("Expecting ','") and re.search(r'\d(?:\.\d*)?(?:[eE][+-]?\d*)?$', line) is not None and tail[:1] in ('.', 'e', 'E')))


def checked_record(record, sid, label):
    kind = record.get('t')
    if not isinstance(kind, str) or kind not in RECORD_SCHEMAS:
        return False
    body = {key: value for key, value in record.items() if key not in ('t', 'session_id', 'round', 'frame')} if kind == 'plan' else record
    fast = FAST_RECORDS.get(kind)
    if fast is None or not fast(body):
        validate(body, ROUND_VALIDATOR if kind == 'learning_round' else VALIDATORS[RECORD_SCHEMAS[kind]], label)
    if record.get('session_id', sid) != sid:
        raise DataError(f'{label}: mismatched session id')
    if kind == 'event' and record['kind'] == 'round_end':
        winner = (record.get('detail') or {}).get('winner')
        if winner is not None and (type(winner) is not int or winner not in (0, 1)):
            raise DataError(f'{label}: invalid round winner')
    return True


def normalized_learning(sid, records, label):
    rounds = {}
    for record in records:
        if record.get('t') == 'learning_round':
            checked_record(record, sid, label)
            rounds[record['round']] = record
    return [rounds[number] for number in sorted(rounds)]


def read_lines(text, label):
    lines = text.splitlines()
    result = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            record = decode(line)
        except json.JSONDecodeError as exc:
            if index == len(lines) - 1 and not text.endswith('\n') and incomplete_json(line, exc):
                break
            raise DataError(f'{label}:{index + 1}: invalid JSON') from exc
        except ValueError as exc:
            raise DataError(f'{label}:{index + 1}: invalid JSON') from exc
        if not isinstance(record, dict):
            raise DataError(f'{label}:{index + 1}: expected object')
        result.append(record)
    return result


class TailReader:
    def __init__(self, path, sid):
        self.path = Path(path)
        self.sid = sid
        self.records = []
        self.offset = 0
        self.mtime = None
        self.generation = 0
        self.skipped = 0
        self.lines = 0
        self.first_error = None
        self.identity = None
        self.digest = hashlib.sha256().digest()

    @traced('file.load')
    def refresh(self):
        for _ in range(3):
            try:
                return self._load()
            except Changed:
                continue
        raise DataError(f'{self.path.name}: changed while being read; retry the request')

    def _load(self):
        with self.path.open('rb') as f:
            st = os.fstat(f.fileno())
            identity = (st.st_dev, st.st_ino)
            if identity == self.identity and st.st_mtime_ns == self.mtime and st.st_size == self.offset:
                return self
            prefix = f.read(min(self.offset, st.st_size))
            if identity != self.identity or st.st_size < self.offset or hashlib.sha256(prefix).digest() != self.digest:
                self.records, self.offset, self.skipped, self.lines, self.first_error = [], 0, 0, 0, None
                self.generation += 1
                f.seek(0)
                prefix = b''
            chunk = f.read(st.st_size - self.offset)
            after = os.fstat(f.fileno())
            if (st.st_size, st.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise Changed()
            end = chunk.rfind(b'\n')
            if end >= 0:
                for raw in chunk[:end + 1].splitlines():
                    self._parse(raw)
                self.offset += end + 1
                prefix += chunk[:end + 1]
            self.digest = hashlib.sha256(prefix).digest()
        self.identity = identity
        self.mtime = st.st_mtime_ns
        return self

    def _parse(self, raw):
        self.lines += 1
        if not raw.strip():
            return
        try:
            record = decode(raw)
            if not isinstance(record, dict):
                raise ValueError('expected object')
            if checked_record(record, self.sid, self.path.name):
                self.records.append(record)
        except (ValueError, UnicodeDecodeError, DataError) as exc:
            self.skipped += 1
            if self.first_error is None:
                detail = str(exc).removeprefix(f'{self.path.name}: ') if isinstance(exc, DataError) else 'invalid JSON'
                self.first_error = f'{self.path.name}:{self.lines}: {detail}'


class FileRepository:
    def __init__(self, data_dir):
        self.root = Path(data_dir).resolve()
        self.lock = threading.RLock()
        self.files = {}
        self.results = {}
        self.parsed = {}
        self.tails = {}
        self.invalid_sessions = {}

    @traced('file.load')
    def _read(self, path, optional=False):
        path = Path(path)
        try:
            for _ in range(2):
                before = path.stat()
                stamp = (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size)
                cached = self.files.get(path)
                if cached and cached[0] == stamp:
                    return stamp, cached[1]
                text = path.read_text(encoding='utf-8')
                after = path.stat()
                if stamp == (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size):
                    self.files[path] = (stamp, text)
                    return stamp, text
            raise DataError(f'{path.name}: changed while being read; retry the request')
        except FileNotFoundError as exc:
            self.files.pop(path, None)
            if optional:
                return None, None
            raise DataError(f'{path.name}: required file is missing') from exc
        except (OSError, UnicodeError) as exc:
            raise DataError(f'{path.name}: cannot read file') from exc

    def _json(self, path, validator):
        stamp, text = self._read(path)
        key = (path, 'json')
        cached = self.parsed.get(key)
        if cached and cached[0] == stamp:
            return stamp, cached[1]
        try:
            value = decode(text)
        except (ValueError, TypeError) as exc:
            raise DataError(f'{path.name}: invalid JSON') from exc
        validate(value, validator, path.name)
        self.parsed[key] = (stamp, value)
        return stamp, value

    def _session(self, path):
        stamp, meta = self._json(path, VALIDATORS['session'])
        for field in ('started_at', 'ended_at'):
            if meta.get(field) is not None:
                try:
                    parsed = datetime.fromisoformat(meta[field].replace('Z', '+00:00'))
                    if parsed.tzinfo is None:
                        raise ValueError('timezone required')
                except ValueError as exc:
                    raise DataError(f'{path.name}: invalid {field} timestamp') from exc
        sid = meta['session_id']
        if not safe_id(sid):
            raise DataError(f'{path.name}: unsafe session id')
        if path.parent == self.root / 'sessions' and path.stem != sid:
            raise DataError(f'{path.name}: session id does not match metadata filename')
        return stamp, meta

    def _sessions(self, requested=None):
        try:
            canonical = sorted((self.root / 'sessions').glob('*.json'))
            samples = sorted((self.root / 'samples').glob('*.session.json'))
        except OSError as exc:
            raise DataError('Cannot discover session metadata') from exc
        found = {}
        self.invalid_sessions = {}
        for path in canonical + samples:
            try:
                stamp, meta = self._session(path)
            except DataError as exc:
                sid = path.stem if path in canonical else path.name.removesuffix('.session.json')
                cached = self.parsed.get((path, 'json'))
                if path not in canonical and cached:
                    sid = cached[1].get('session_id', sid)
                elif path not in canonical:
                    try:
                        with path.with_name(sid + '.jsonl').open() as stream:
                            first = next(line for line in stream if line.strip())
                        sid = decode(first).get('session_id', sid)
                    except (OSError, ValueError, StopIteration, AttributeError):
                        pass
                if safe_id(sid) and sid not in found:
                    self.invalid_sessions[sid] = exc
                logger.warning('Session metadata unavailable: %s', exc)
                continue
            sid = meta['session_id']
            if sid in self.invalid_sessions:
                continue
            sample = path.with_name(path.name.removesuffix('.session.json') + '.jsonl')
            if sid in found:
                previous = found[sid]
                if path.parent == self.root / 'samples' and sample.is_file() and not previous[2].get('recording') and not previous[3].is_file():
                    found[sid] = (*previous[:3], sample.resolve())
                continue
            if path.parent == self.root / 'samples':
                if not sample.is_file():
                    continue
                recording = sample
            else:
                default = self.root / 'recordings' / f'{sid}.jsonl'
                reference = Path(meta.get('recording') or default)
                recording = reference if reference.is_absolute() else ROOT / reference
                if not reference.is_absolute() and not recording.is_file() and default.is_file():
                    recording = default
            found[sid] = (path, stamp, meta, recording.resolve())
        self.results = {key: value for key, value in self.results.items() if key[0] in found}
        if requested in self.invalid_sessions:
            raise self.invalid_sessions[requested]
        return found

    def _learning(self, sid):
        path = self.root / 'learning' / f'{sid}.jsonl'
        stamp, text = self._read(path, optional=True)
        key = (path, 'learning')
        cached = self.parsed.get(key)
        if cached and cached[0] == stamp:
            return stamp, cached[1]
        result = normalized_learning(sid, read_lines(text, path.name) if text is not None else [], path.name)
        self.parsed[key] = (stamp, result)
        return stamp, result

    def _evaluation(self, sid):
        path = self.root / 'eval' / f'{sid}.json'
        stamp, text = self._read(path, optional=True)
        if text is None:
            return stamp, {'before': None, 'after': None}
        try:
            value = decode(text)
        except ValueError as exc:
            raise DataError(f'{path.name}: invalid evaluation JSON') from exc
        validate(value, EVAL_VALIDATOR, path.name)
        return stamp, {key: value[key] for key in ('before', 'after')}

    def _metrics(self, sid):
        from analytics.metrics import learning_metrics

        learning_stamp, rounds = self._learning(sid)
        eval_stamp, evaluation = self._evaluation(sid)
        signature = (learning_stamp, eval_stamp)
        key = (sid, 'learning')
        cached = self.results.get(key)
        if cached and cached[0] == signature:
            return signature, cached[1]
        body = learning_metrics(sid, rounds, evaluation)
        validate(body, VALIDATORS['metrics'], f'learning response for {sid}')
        self.results[key] = (signature, body)
        return signature, body

    def learning(self, sid):
        with self.lock:
            if not safe_id(sid) or sid not in self._sessions(sid):
                return None
            return copy.deepcopy(self._metrics(sid)[1])

    def _tail(self, recording, sid):
        tail = self.tails.get(recording)
        if tail is None or tail.sid != sid:
            tail = TailReader(recording, sid)
        try:
            tail.refresh()
        except FileNotFoundError as exc:
            self.tails.pop(recording, None)
            raise DataError(f'{recording.name}: required file is missing') from exc
        except OSError as exc:
            raise DataError(f'{recording.name}: cannot read file') from exc
        self.tails[recording] = tail
        return tail

    def _records(self, path, sid):
        tail = self._tail(Path(path), sid)
        if tail.skipped:
            raise DataError(tail.first_error)
        stamp = (tail.generation, tail.offset)
        key = (Path(path), 'records')
        cached = self.parsed.get(key)
        if cached and cached[0] == stamp and cached[1] == sid:
            return stamp, cached[2]
        records = [record for record in tail.records if record['t'] in ('state', 'event', 'round_summary')]
        self.parsed[key] = (stamp, sid, records)
        return stamp, records

    def stats(self, sid):
        from analytics.stats import compute

        with self.lock:
            sessions = self._sessions(sid) if safe_id(sid) else {}
            if sid not in sessions:
                return None
            _, meta_stamp, meta, recording = sessions[sid]
            tail = self._tail(recording, sid)
            signature = (meta_stamp, tail.generation, tail.offset)
            cached = self.results.get((sid, 'stats'))
            if cached and cached[0] == signature:
                return copy.deepcopy(cached[1])
            body = compute(sid, meta, [r for r in tail.records if r.get('session_id', sid) == sid])
            body['skipped_lines'] = tail.skipped
            self.results[(sid, 'stats')] = (signature, body)
            return copy.deepcopy(body)

    def trends(self, player, character, stat=None):
        from analytics.metrics import trend_values

        with self.lock:
            series = []
            for sid, (meta_path, meta_stamp, meta, recording) in self._sessions().items():
                if meta['player'] != player or meta['human_character'] != character:
                    continue
                record_stamp, records = self._records(recording, sid)
                metrics_stamp, metrics = self._metrics(sid)
                signature = (meta_path, meta_stamp, recording, record_stamp, metrics_stamp)
                cached = self.results.get((sid, 'trends'))
                if cached and cached[0] == signature:
                    values = cached[1]
                else:
                    values = trend_values(meta, records, metrics)
                    self.results[(sid, 'trends')] = (signature, values)
                selected = values if stat is None else {stat: values[stat]} if stat in values else {}
                series.append({'session_id': sid, 'started_at': meta['started_at'], 'values': copy.deepcopy(selected)})
            series.sort(key=lambda point: (datetime.fromisoformat(point['started_at'].replace('Z', '+00:00')), point['session_id']))
            return {'player': player, 'character': character, 'series': series}
