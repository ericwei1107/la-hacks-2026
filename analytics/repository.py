import copy
import json
import threading
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = {p.name.removesuffix('.schema.json'): json.loads(p.read_text()) for p in (ROOT / 'contracts').glob('*.schema.json')}
VALIDATORS = {name: Draft202012Validator(schema, format_checker=FormatChecker()) for name, schema in SCHEMAS.items()}
ROUND_VALIDATOR = Draft202012Validator({**SCHEMAS['metrics']['$defs']['round'], '$defs': SCHEMAS['metrics']['$defs']}, format_checker=FormatChecker())
EVAL_VALIDATOR = Draft202012Validator({'type': 'object', 'required': ['before', 'after'], 'properties': {key: {'type': ['number', 'null'], 'minimum': 0, 'maximum': 1} for key in ('before', 'after')}})


class DataError(Exception):
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


def read_lines(text, label):
    lines = text.splitlines()
    result = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            record = decode(line)
        except json.JSONDecodeError as exc:
            incomplete = exc.pos >= len(line.rstrip()) - 1 or exc.msg.startswith('Unterminated string')
            if index == len(lines) - 1 and not text.endswith('\n') and line.lstrip().startswith('{') and incomplete:
                break
            raise DataError(f'{label}: invalid JSON at line {index + 1}') from exc
        except ValueError as exc:
            raise DataError(f'{label}: invalid JSON at line {index + 1}') from exc
        if not isinstance(record, dict):
            raise DataError(f'{label}: expected object at line {index + 1}')
        result.append(record)
    return result


class TailReader:
    def __init__(self, path):
        self.path = Path(path)
        self.records = []
        self.offset = 0
        self.mtime = None
        self.generation = 0
        self.skipped = 0

    def refresh(self):
        st = self.path.stat()
        if st.st_size < self.offset or (st.st_size == self.offset and self.mtime is not None and st.st_mtime_ns != self.mtime):
            self.records, self.offset, self.skipped = [], 0, 0
            self.generation += 1
        if st.st_size > self.offset:
            with open(self.path, 'rb') as f:
                f.seek(self.offset)
                chunk = f.read(st.st_size - self.offset)
            end = chunk.rfind(b'\n')
            if end >= 0:
                for raw in chunk[:end + 1].splitlines():
                    self._parse(raw)
                self.offset += end + 1
        self.mtime = st.st_mtime_ns
        return self

    def _parse(self, raw):
        if not raw.strip():
            return
        try:
            record = decode(raw)
        except (ValueError, UnicodeDecodeError):
            self.skipped += 1
            return
        if isinstance(record, dict) and isinstance(record.get('t'), str):
            self.records.append(record)
        else:
            self.skipped += 1


class FileRepository:
    def __init__(self, data_dir):
        self.root = Path(data_dir).resolve()
        self.lock = threading.RLock()
        self.files = {}
        self.results = {}
        self.parsed = {}
        self.tails = {}

    def _read(self, path, optional=False):
        path = Path(path)
        try:
            for _ in range(2):
                before = path.stat()
                stamp = (before.st_mtime_ns, before.st_size)
                cached = self.files.get(path)
                if cached and cached[0] == stamp:
                    return stamp, cached[1]
                text = path.read_text(encoding='utf-8')
                after = path.stat()
                if stamp == (after.st_mtime_ns, after.st_size):
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

    def _sessions(self):
        try:
            canonical = sorted((self.root / 'sessions').glob('*.json'))
            samples = sorted((self.root / 'samples').glob('*.session.json'))
        except OSError as exc:
            raise DataError('Cannot discover session metadata') from exc
        found = {}
        for path in canonical + samples:
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
                reference = Path(meta.get('recording') or self.root / 'recordings' / f'{sid}.jsonl')
                recording = reference if reference.is_absolute() else ROOT / reference
            found[sid] = (path, stamp, meta, recording.resolve())
        self.results = {key: value for key, value in self.results.items() if key[0] in found}
        return found

    def _learning(self, sid):
        path = self.root / 'learning' / f'{sid}.jsonl'
        stamp, text = self._read(path, optional=True)
        key = (path, 'learning')
        cached = self.parsed.get(key)
        if cached and cached[0] == stamp:
            return stamp, cached[1]
        rounds = {}
        if text is not None:
            for record in read_lines(text, path.name):
                if record.get('t') != 'learning_round':
                    continue
                validate(record, ROUND_VALIDATOR, path.name)
                if record.get('session_id', sid) != sid:
                    raise DataError(f'{path.name}: mismatched session id')
                rounds[record['round']] = record
        result = [rounds[number] for number in sorted(rounds)]
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
            if not safe_id(sid) or sid not in self._sessions():
                return None
            return copy.deepcopy(self._metrics(sid)[1])

    def _records(self, path, sid):
        stamp, text = self._read(path)
        key = (path, 'records')
        cached = self.parsed.get(key)
        if cached and cached[0] == stamp and cached[1] == sid:
            return stamp, cached[2]
        records = []
        names = {'state': 'gamestate', 'event': 'event', 'round_summary': 'round_summary', 'plan': 'gameplan', 'learning_round': 'metrics'}
        for record in read_lines(text, path.name):
            kind = record.get('t')
            if not isinstance(kind, str) or kind not in names:
                continue
            body = record
            if kind == 'plan':
                body = {key: value for key, value in record.items() if key not in ('t', 'session_id', 'round', 'frame')}
            validate(body, ROUND_VALIDATOR if kind == 'learning_round' else VALIDATORS[names[kind]], path.name)
            if record.get('session_id') != sid:
                raise DataError(f'{path.name}: mismatched session id')
            if kind in ('event', 'round_summary'):
                records.append(record)
        self.parsed[key] = (stamp, sid, records)
        return stamp, records

    def stats(self, sid):
        from analytics.stats import compute

        with self.lock:
            sessions = self._sessions() if safe_id(sid) else {}
            if sid not in sessions:
                return None
            _, meta_stamp, meta, recording = sessions[sid]
            tail = self.tails.get(recording) or TailReader(recording)
            try:
                tail.refresh()
            except FileNotFoundError as exc:
                self.tails.pop(recording, None)
                raise DataError(f'{recording.name}: required file is missing') from exc
            except OSError as exc:
                raise DataError(f'{recording.name}: cannot read file') from exc
            self.tails[recording] = tail
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
