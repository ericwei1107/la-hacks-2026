import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from analytics.metrics import learning_metrics, trend_values
from analytics.repository import DataError, FileRepository

FORMAT = 1


def signature(repository, meta, recording):
    sid = meta['session_id']
    content = [meta]
    for path, optional in ((recording, False), (repository.root / 'learning' / f'{sid}.jsonl', True), (repository.root / 'eval' / f'{sid}.json', True)):
        stamp, text = repository._read(path, optional=optional)
        key = (path, 'tiger-fingerprint')
        cached = repository.parsed.get(key)
        if cached and cached[0] == stamp:
            digest = cached[1]
        else:
            digest = hashlib.sha256(text.encode()).hexdigest() if text is not None else None
            repository.parsed[key] = (stamp, digest)
        content.append(digest)
    return hashlib.sha256(json.dumps([FORMAT, content], sort_keys=True, allow_nan=False, separators=(',', ':')).encode()).hexdigest()


@dataclass(frozen=True)
class TrendSnapshot:
    meta: dict
    signature: str
    eligible: bool
    rows: list


def snapshot(data_dir, meta, recording, batches):
    repository = FileRepository(data_dir)
    initial = signature(repository, meta, recording)
    _, records = repository._records(recording, meta['session_id'])
    _, metrics = repository._metrics(meta['session_id'])
    closed = {batch.number for batch in batches}
    from analytics.tigerdata.source import records as raw_records

    eligible = all(record['round'] in closed for _, _, record in raw_records(recording, meta['session_id'], 'recording'))
    eligible = eligible and all(record['round'] in closed for record in metrics['rounds'])
    eligible = eligible and all(record['round'] in closed for record in meta['rounds'] if record.get('winner') is not None)
    rows = []
    for batch in batches:
        number = batch.number
        prefix_meta = {**meta, 'rounds': [record for record in meta['rounds'] if record['round'] <= number]}
        prefix_metrics = learning_metrics(meta['session_id'], [record for record in metrics['rounds'] if record['round'] <= number], metrics['finetune'])
        values = trend_values(prefix_meta, [record for record in records if record['round'] <= number], prefix_metrics)
        moment = max(row.observed_at for group in batch.rows.values() for row in group)
        rows.extend((moment, meta['session_id'], number, key, value) for key, value in values.items())
    fresh = FileRepository(data_dir)
    current = fresh._sessions().get(meta['session_id'])
    if not current or current[2] != meta or current[3] != recording or initial != signature(fresh, meta, recording):
        raise DataError(f"{meta['session_id']}: source changed during trend calculation; retry")
    return TrendSnapshot(meta, initial, eligible and bool(batches), rows)


def assemble(player, character, points, stat=None):
    series = []
    for meta, values in points:
        selected = values if stat is None else {stat: values[stat]} if stat in values else {}
        series.append({'session_id': meta['session_id'], 'started_at': meta['started_at'], 'values': selected})
    series.sort(key=lambda point: (datetime.fromisoformat(point['started_at'].replace('Z', '+00:00')), point['session_id']))
    return {'player': player, 'character': character, 'series': series}
