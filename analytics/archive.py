import argparse
import hashlib
import json
import os
import sys
import tempfile
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from analytics.repository import ROOT, VALIDATORS, DataError, decode, incomplete_json, safe_id, validate


class ArchiveError(ValueError):
    pass


@dataclass(frozen=True)
class Source:
    path: Path
    member: str | None = None
    meta: dict | None = None
    priority: int = 0
    sid: str | None = None

    @property
    def label(self):
        return f'{self.path}:{self.member}' if self.member else str(self.path)

    @contextmanager
    def open(self):
        if self.member is None:
            with self.path.open('rb') as stream:
                yield stream
        else:
            with zipfile.ZipFile(self.path) as archive:
                with archive.open(self.member) as stream:
                    yield stream


def metadata(text, label):
    try:
        value = decode(text)
        validate(value, VALIDATORS['session'], label)
    except (ValueError, DataError) as exc:
        raise ArchiveError(f'{label}: invalid session metadata') from exc
    if not safe_id(value['session_id']):
        raise ArchiveError(f'{label}: unsafe session id')
    return value


def parse_line(raw, number):
    try:
        text = raw.decode('utf-8').removesuffix('\n').removesuffix('\r')
    except UnicodeDecodeError as exc:
        if not raw.endswith(b'\n') and exc.reason == 'unexpected end of data' and exc.end == len(raw):
            return None
        raise ArchiveError(f'line {number}: invalid UTF-8') from exc
    try:
        record = decode(text)
    except json.JSONDecodeError as exc:
        if not raw.endswith(b'\n') and incomplete_json(text, exc):
            return None
        raise ArchiveError(f'line {number}: malformed JSON') from exc
    return text, record


def identify(source):
    sid = source.meta['session_id'] if source.meta else None
    if sid is None:
        with source.open() as stream:
            for number, raw in enumerate(stream, 1):
                if not raw.strip():
                    continue
                parsed = parse_line(raw, number)
                if parsed is None:
                    break
                _, record = parsed
                if not isinstance(record, dict):
                    raise ArchiveError(f'{source.label}: expected JSON object')
                sid = record.get('session_id')
                break
        if sid is None:
            sid = Path(source.member or source.path.name).stem
    if not safe_id(sid):
        raise ArchiveError(f'{source.label}: unsafe session id')
    return replace(source, sid=sid)


def discover(data_dir):
    root = Path(data_dir).resolve()
    if not root.is_dir():
        raise ArchiveError(f'{root}: data directory does not exist')
    samples = root / 'samples'
    candidates = []
    errors = []
    dataset_roots = [root] + sorted({path.parent for path in samples.rglob('sessions') if path.is_dir()})
    referenced = set()
    for dataset in dataset_roots:
        for path in sorted((dataset / 'sessions').glob('*.json')):
            try:
                meta = metadata(path.read_text(encoding='utf-8'), str(path))
                if path.stem != meta['session_id']:
                    raise ArchiveError(f'{path}: session id does not match metadata filename')
                reference = meta.get('recording')
                recording = Path(reference) if reference else dataset / 'recordings' / f"{meta['session_id']}.jsonl"
                if not recording.is_absolute():
                    recording = ROOT / recording
                recording = recording.resolve()
                referenced.add(recording)
                candidates.append(Source(recording, meta=meta, priority=0 if dataset == root else 2))
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
    plain = sorted((root / 'recordings').glob('*.jsonl')) + sorted(samples.rglob('*.jsonl'))
    for path in plain:
        if path.resolve() in referenced or path.name.endswith('.learning.jsonl') or 'learning' in path.relative_to(root).parts[:-1]:
            continue
        try:
            paired = path.with_suffix('.session.json')
            meta = metadata(paired.read_text(encoding='utf-8'), str(paired)) if paired.exists() else None
            candidates.append(Source(path.resolve(), meta=meta, priority=1 if path.parent == root / 'recordings' else 2))
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    for path in sorted(samples.rglob('*.zip')):
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                if len(names) != len(set(names)):
                    raise ArchiveError(f'{path}: duplicate ZIP member names')
                for name in sorted(names):
                    if not name.endswith('.jsonl') or name.endswith('.learning.jsonl') or 'learning' in Path(name).parts[:-1]:
                        continue
                    paired = name.removesuffix('.jsonl') + '.session.json'
                    meta = metadata(archive.read(paired), f'{path}:{paired}') if paired in names else None
                    candidates.append(Source(path.resolve(), member=name, meta=meta, priority=3))
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
            errors.append(str(exc))
    found = {}
    conflicts = set()
    for source in sorted(candidates, key=lambda item: (item.priority, item.label)):
        try:
            source = identify(source)
            previous = found.get(source.sid)
            if previous and previous.priority == source.priority and previous.label != source.label:
                conflicts.add(source.sid)
                errors.append(f'{source.sid}: ambiguous recording sources: {previous.label}, {source.label}')
            elif previous is None:
                found[source.sid] = source
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
            errors.append(f'{source.label}: {exc}')
    return [found[sid] for sid in sorted(found) if sid not in conflicts], errors


def stamp(path):
    value = path.stat()
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def row(record, text, sid, number):
    if not isinstance(record, dict):
        raise ArchiveError(f'line {number}: expected JSON object')
    if record.get('session_id', sid) != sid:
        raise ArchiveError(f'line {number}: session id mismatch')
    kind = record.get('t')
    if kind is not None and not isinstance(kind, str):
        raise ArchiveError(f'line {number}: invalid record type')
    for key in ('round', 'frame'):
        value = record.get(key)
        if value is not None and (type(value) is not int or not -(2**63) <= value < 2**63):
            raise ArchiveError(f'line {number}: invalid {key}')
    return {'session_id': sid, 't': kind, 'round': record.get('round'), 'frame': record.get('frame'), 'source_line': number, 'record_json': text}


def archive_source(source, output_dir, batch_size=8192):
    import pyarrow as pa
    import pyarrow.parquet as pq

    if batch_size < 1:
        raise ArchiveError('batch size must be positive')
    if not safe_id(source.sid):
        raise ArchiveError('unsafe session id')
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f'{source.sid}.parquet'
    initial = stamp(source.path)
    schema = pa.schema([
        ('session_id', pa.string()), ('t', pa.string()), ('round', pa.int64()),
        ('frame', pa.int64()), ('source_line', pa.int64()), ('record_json', pa.string()),
    ])
    digest = hashlib.sha256()
    count = 0
    truncated = False
    with tempfile.NamedTemporaryFile(dir=output, prefix=f'.{source.sid}.', suffix='.tmp', delete=False) as temporary:
        pending = Path(temporary.name)
    try:
        with pq.ParquetWriter(pending, schema, compression='zstd') as writer:
            batch = []
            with source.open() as stream:
                for number, raw in enumerate(stream, 1):
                    digest.update(raw)
                    if not raw.strip():
                        continue
                    parsed = parse_line(raw, number)
                    if parsed is None:
                        truncated = True
                        break
                    text, record = parsed
                    batch.append(row(record, text, source.sid, number))
                    count += 1
                    if len(batch) == batch_size:
                        writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                        batch.clear()
            if batch:
                writer.write_table(pa.Table.from_pylist(batch, schema=schema))
            writer.add_key_value_metadata({
                'kumite.archive_version': '1', 'kumite.session_id': source.sid,
                'kumite.source': source.label, 'kumite.source_sha256': digest.hexdigest(),
                'kumite.rows': str(count), 'kumite.incomplete_tail': json.dumps(truncated),
                'kumite.session_metadata': json.dumps(source.meta, ensure_ascii=False, allow_nan=False),
            })
        if stamp(source.path) != initial:
            raise ArchiveError('source changed during conversion; retry after recording stops')
        if pq.read_metadata(pending).num_rows != count:
            raise ArchiveError('Parquet row count verification failed')
        os.replace(pending, destination)
    finally:
        pending.unlink(missing_ok=True)
    return destination, count, truncated


def main(argv=None):
    parser = argparse.ArgumentParser(description='Archive session recordings as lossless Parquet snapshots')
    parser.add_argument('--data-dir', default=os.environ.get('DATA_DIR', './data'))
    parser.add_argument('--output-dir', help='Output directory (default: DATA_DIR/archive)')
    args = parser.parse_args(argv)
    try:
        import pyarrow as pa
    except ImportError:
        print('Install archive dependencies: python -m pip install -r analytics/requirements-archive.txt', file=sys.stderr)
        return 2
    try:
        sources, errors = discover(args.data_dir)
    except (OSError, ValueError) as exc:
        print(f'Archive failed: {exc}', file=sys.stderr)
        return 1
    archived = 0
    for source in sources:
        try:
            path, count, truncated = archive_source(source, args.output_dir or Path(args.data_dir) / 'archive')
            suffix = ' (incomplete tail omitted; rerun after recording stops)' if truncated else ''
            print(f'{source.sid}: rows={count} -> {path}{suffix}')
            archived += 1
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, pa.ArrowException) as exc:
            errors.append(f'{source.label}: {exc}')
    for error in errors:
        print(f'Archive failed: {error}', file=sys.stderr)
    print(f'Sessions archived={archived} failed={len(errors)}')
    return 1 if errors else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
