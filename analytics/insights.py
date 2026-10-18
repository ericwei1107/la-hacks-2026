import argparse
import copy
import hashlib
import json
import os
import re
import tempfile
import threading
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

from analytics.evidence import METRIC_ORDER, analyze, reference
from analytics.focus import RULE_VERSION, select
from analytics.metrics import learning_metrics
from analytics.observability import traced
from analytics.repository import DataError, FileRepository, ROOT, VALIDATORS, checked_record, decode, incomplete_json, normalized_learning, validate
from analytics.stats import CALCULATION_VERSION

FORMAT_VERSION = 1
HISTORY_LIMIT = 50
SNAPSHOT_VALIDATOR = Draft202012Validator(json.loads(Path(__file__).with_name('insights.schema.json').read_text()))
PUBLIC_FORMAT_VERSION = 1
PUBLIC_LIMIT = 5
PUBLIC_VALIDATOR = Draft202012Validator(json.loads(Path(__file__).with_name('insights_v1.schema.json').read_text()))


def encoded(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def check_id(sid):
    if not isinstance(sid, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,179}', sid):
        raise ValueError('Invalid session id')
    if sid.split('.')[0].split('_')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        raise ValueError('Invalid session id')


def stamp(path):
    try:
        st = path.stat()
        return st.st_dev, st.st_ino, st.st_mtime_ns, st.st_size
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise DataError('Cannot inspect insight source') from exc


def read_bytes(path, optional=False):
    try:
        with path.open('rb') as stream:
            before = os.fstat(stream.fileno())
            content = stream.read()
            after = os.fstat(stream.fileno())
        expected = (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size)
        if expected != (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size):
            raise DataError('Insight source changed during capture; retry')
        return expected, content
    except FileNotFoundError as exc:
        if optional:
            return None, None
        raise DataError('Required insight source is missing') from exc
    except OSError as exc:
        raise DataError('Cannot read insight source') from exc


def prefix(raw, recording=False):
    if raw is None:
        return None, False
    end = raw.rfind(b'\n') + 1
    if recording:
        return raw[:end], bool(raw[end:])
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        if exc.reason == 'unexpected end of data' and exc.end == len(raw) and exc.start >= end:
            return raw[:end], True
        raise DataError('Learning source contains invalid UTF-8') from exc
    tail = text.splitlines()[-1] if text.splitlines() else ''
    if not raw.endswith(b'\n') and tail.strip():
        try:
            decode(tail)
        except json.JSONDecodeError as exc:
            if incomplete_json(tail, exc):
                return raw[:end], True
        except ValueError:
            pass
    return raw, False


def describe(raw, pending=False):
    return {'available': raw is not None, 'sha256': digest(raw) if raw is not None else None,
            'consumed_bytes': len(raw) if raw is not None else 0, 'pending_tail': pending}


def recording_records(raw, sid):
    entries, tactical, invalid = [], [], []
    unsupported = 0
    for line, content in enumerate(raw.splitlines(), 1):
        if not content.strip():
            continue
        try:
            record = decode(content)
            if not isinstance(record, dict):
                raise ValueError('Expected object')
            if record.get('t') == 'tactical':
                if (record.get('session_id') == sid and type(record.get('round')) is int and record['round'] > 0
                        and type(record.get('frame')) is int and record['frame'] >= 0
                        and isinstance(record.get('chosen'), str) and isinstance(record.get('source'), str)):
                    tactical.append((line, record))
                else:
                    unsupported += 1
            elif checked_record(record, sid, 'recording'):
                entries.append((line, record))
            else:
                unsupported += 1
        except (ValueError, UnicodeError, DataError):
            invalid.append(line)
    return entries, tactical, invalid, unsupported


def learning_records(raw, sid):
    if raw is None:
        return []
    records = []
    try:
        for content in raw.decode('utf-8').splitlines():
            if content.strip():
                record = decode(content)
                if not isinstance(record, dict):
                    raise ValueError('Expected object')
                records.append(record)
        return normalized_learning(sid, records, 'learning')
    except (ValueError, UnicodeError) as exc:
        raise DataError('Invalid complete learning data') from exc


def bounded_metrics(metrics, limit):
    result = copy.deepcopy(metrics)
    for metric in result.values():
        metric['evidence_total'] = len(metric['evidence'])
        metric['evidence'] = metric['evidence'][:min(limit, 3)]
    return result


def habit_history(rounds, summaries):
    result = {}
    for record in rounds:
        for key, value in record['habits'].items():
            row = result.setdefault(key, {'first_detected_round': None, 'first_fixed_round': None, 'current': None, 'history': []})
            if row['first_detected_round'] is None and value['n'] >= 4 and value['p'] >= 0.6:
                row['first_detected_round'] = record['round']
            if row['first_fixed_round'] is None and value.get('fixed') is True:
                row['first_fixed_round'] = record['round']
            observed = {'round': record['round'], **copy.deepcopy(value)}
            observed['regressed'] = key in summaries.get(record['round'], {}).get('regressed', [])
            row['current'] = observed
            row['history'].append(observed)
    for row in result.values():
        row['history_total'] = len(row['history'])
        row['history'] = row['history'][-HISTORY_LIMIT:]
    return result


EVENT_FIELDS = ('kind', 'actor', 'target', 'damage', 'hit_level', 'move_id', 'frame_advantage')


def event_summary(event):
    return {key: event[key] for key in EVENT_FIELDS if key in event}


def with_events(metrics, entries):
    by_line = dict(entries)
    for metric in metrics.values():
        for item in metric['evidence']:
            item['event'] = event_summary(by_line[item['opportunity']['line']])
    return metrics


def moments(entries, metrics, human, sid, source_hash, completed, limit):
    candidates = {}
    for key in METRIC_ORDER:
        for item in metrics[key]['evidence']:
            ref = item['opportunity']
            row = candidates.setdefault(ref['line'], {'reference': ref, 'metrics': [], 'outcome': item['outcome'], 'response': item['response'], 'metric_outcomes': {}})
            row['metrics'].append(key)
            row['metric_outcomes'][key] = {'outcome': item['outcome'], 'response': item['response']}
            outcomes = {value['outcome'] for value in row['metric_outcomes'].values()}
            row['outcome'] = next(iter(outcomes)) if len(outcomes) == 1 else 'mixed'
            if len(row['metrics']) > 1:
                row['response'] = None
    for line, event in entries:
        if (event.get('t') == 'event' and event['round'] in completed and event.get('target') == human
                and event.get('kind') in ('hit', 'counter_hit', 'throw') and (event.get('damage') or 0) > 0):
            candidates.setdefault(line, {'reference': reference(sid, source_hash, line, event), 'metrics': [], 'outcome': 'damage', 'response': None, 'metric_outcomes': {}})
    by_line = dict(entries)
    ranked = sorted(candidates, key=lambda line: (candidates[line]['outcome'] == 'success', -(by_line[line].get('damage') or 0), line))[:limit]
    selected = []
    for line in sorted(ranked):
        row = candidates[line]
        event = by_line[line]
        row['event'] = event_summary(event)
        selected.append(row)
    return selected, len(candidates)


class InsightRepository:
    def __init__(self, data_dir, brain_files_only=False):
        self.root = Path(data_dir).resolve()
        self.brain_files_only = brain_files_only
        self.files = FileRepository(self.root)
        self.lock = threading.RLock()
        self.cache = {}

    def capture(self, sid):
        check_id(sid)
        for attempt in range(2):
            try:
                with self.files.lock:
                    session = self.files._sessions(sid).get(sid)
                if session is None:
                    return None
                meta_path, _, expected_meta, recording = session
                if self.brain_files_only and not (recording.is_relative_to(self.root) and meta_path.resolve().is_relative_to(self.root)):
                    raise DataError('Insight source is outside DATA_DIR')
                paths = {'metadata': meta_path, 'recording': recording,
                         'learning': self.root / 'learning' / f'{sid}.jsonl',
                         'evaluation': self.root / 'eval' / f'{sid}.json'}
                if not self.brain_files_only:
                    paths['report'] = self.root / 'reports' / f'{sid}.json'
                captured = {key: read_bytes(path, optional=key not in ('metadata', 'recording')) for key, path in paths.items()}
                if any(stamp(path) != captured[key][0] for key, path in paths.items()):
                    raise DataError('Insight source changed during capture; retry')
                metadata = decode(captured['metadata'][1])
                validate(metadata, VALIDATORS['session'], 'metadata')
                if metadata != expected_meta:
                    self.files.files.pop(meta_path, None)
                    self.files.parsed.pop((meta_path, 'json'), None)
                    raise DataError('Metadata changed during capture; retry')
                raw = {key: value[1] for key, value in captured.items()}
                raw.setdefault('report', None)
                recording_prefix, recording_pending = prefix(raw['recording'], recording=True)
                learning_prefix, learning_pending = prefix(raw['learning'])
                sources = {key: describe(value) for key, value in raw.items()}
                sources['recording'] = describe(recording_prefix, recording_pending)
                sources['learning'] = describe(learning_prefix, learning_pending)
                raw['recording'], raw['learning'] = recording_prefix, learning_prefix
                return metadata, raw, sources
            except (DataError, ValueError, UnicodeError) as exc:
                if attempt:
                    raise DataError('Cannot capture a consistent, valid insight source') from exc
        raise DataError('Cannot capture insight source')

    @traced('insights.derive')
    def snapshot(self, sid, limit=10, focus=None):
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError('Moment limit must be between 1 and 50')
        with self.lock:
            captured = self.capture(sid)
            if captured is None:
                return None
            meta, raw, sources = captured
            revision = digest(encoded({'sources': sources, 'format_version': FORMAT_VERSION,
                                      'calculation_version': CALCULATION_VERSION, 'rule_version': RULE_VERSION}))
            key = sid, revision, limit, focus
            if key in self.cache:
                return copy.deepcopy(self.cache[key])
            entries, tactical, invalid, unsupported = recording_records(raw['recording'], sid)
            records = [record for line, record in entries]
            completed = sorted({r['round'] for r in records if r['t'] == 'round_summary' or (r['t'] == 'event' and r['kind'] == 'round_end')})
            completed_entries = [(line, record) for line, record in entries if record.get('round') in completed]
            rounds = learning_records(raw['learning'], sid)
            recording_rounds = {r['round'] for r in records if type(r.get('round')) is int}
            ahead = sorted({r['round'] for r in rounds} - set(completed))
            completed_learning = [r for r in rounds if r['round'] in completed]
            evaluation = {'before': None, 'after': None}
            if raw['evaluation'] is not None:
                from analytics.repository import EVAL_VALIDATOR
                try:
                    value = decode(raw['evaluation'])
                except (ValueError, UnicodeError) as exc:
                    raise DataError('Invalid evaluation data') from exc
                validate(value, EVAL_VALIDATOR, 'evaluation')
                evaluation = {name: value[name] for name in evaluation}
            metrics = analyze(completed_entries, meta['human_slot'], sid, sources['recording']['sha256'], bool(invalid))
            summaries = {r['round']: r for r in records if r['t'] == 'round_summary'}
            learning = learning_metrics(sid, completed_learning, evaluation)
            picked, total_moments = moments(completed_entries, metrics, meta['human_slot'], sid, sources['recording']['sha256'], completed, limit)
            waiting = sorted(set(completed) - {r['round'] for r in completed_learning})
            report = {'status': 'unavailable', 'used_for_recommendation': False}
            if raw['report'] is not None:
                try:
                    body = decode(raw['report'])
                    validate(body, VALIDATORS['report'], 'report')
                    if body['session_id'] != sid:
                        raise DataError('Mismatched report session')
                    report['status'] = 'available_unverified_revision'
                except (ValueError, UnicodeError, DataError):
                    report['status'] = 'invalid'
            tactical_closed = [r for line, r in tactical if r['round'] in completed]
            result = {
                'format_version': FORMAT_VERSION, 'calculation_version': CALCULATION_VERSION, 'rule_version': RULE_VERSION,
                'snapshot_id': revision, 'session_id': sid, 'synthetic': meta['mode'] == 'synthetic' if 'mode' in meta else None,
                'population': 'completed_rounds', 'sources': sources,
                'freshness': {'latest_recording_round': max(recording_rounds, default=None), 'completed_rounds': completed,
                              'latest_learning_round': max((r['round'] for r in rounds), default=None),
                              'pending_learning_rounds': waiting, 'learning_ahead_rounds': ahead},
                'quality': {'state': 'invalid' if invalid else 'pending' if waiting or ahead or any(s['pending_tail'] for s in sources.values()) else 'observed',
                            'skipped_recording_lines': len(invalid), 'invalid_line_positions': invalid[:50],
                            'unsupported_records': unsupported, 'deliberate_retests': 'unavailable'},
                'metrics': with_events(bounded_metrics(metrics, limit), completed_entries),
                'rounds': [{'round': number, 'metrics': bounded_metrics(analyze([(line, r) for line, r in completed_entries if r['round'] == number], meta['human_slot'], sid, sources['recording']['sha256'], bool(invalid)), limit)} for number in completed[-HISTORY_LIMIT:]],
                'rounds_total': len(completed), 'focus': select(metrics, focus),
                'learning': {'habits': habit_history(completed_learning, summaries),
                             'prediction_accuracy': [{'round': r['round'], 'value': r['prediction_accuracy'], 'eligible_count': None,
                                                      'player_changed': r.get('player_changed', False)} for r in completed_learning[-HISTORY_LIMIT:]],
                             'bandit_estimates': copy.deepcopy(completed_learning[-1].get('bandit', {})) if completed_learning else {},
                             'finetune': learning['finetune']},
                'tactical': {'chosen_counts': dict(sorted(Counter(r['chosen'] for r in tactical_closed).items())),
                             'habit_driven_decisions': sum(r['source'] == 'habit' for r in tactical_closed),
                             'reflex_records': sum(r['source'] == 'reflex' for r in tactical_closed),
                             'interpretation': 'Recorded choices, not hit rates or calibrated probabilities'},
                'moments': picked, 'moments_total': total_moments, 'report': report,
            }
            validate(result, SNAPSHOT_VALIDATOR, 'internal insight snapshot')
            self.cache = {k: v for k, v in self.cache.items() if k[0] != sid}
            self.cache[key] = copy.deepcopy(result)
            return result

    def resolve(self, sid, snapshot_id, line):
        if type(line) is not int or line < 1:
            raise ValueError('Invalid source line')
        with self.lock:
            current = self.snapshot(sid)
            if current is None:
                return None
            if current['snapshot_id'] != snapshot_id:
                raise DataError('Stale evidence reference; refresh the snapshot')
            captured = self.capture(sid)
            if captured is None or captured[2] != current['sources']:
                raise DataError('Stale evidence reference; refresh the snapshot')
            entries, _, _, _ = recording_records(captured[1]['recording'], sid)
            found = next((r for n, r in entries if n == line), None)
            if found is None or type(found.get('round')) is not int:
                return None
            previous = [(n, r) for n, r in entries if r['t'] == 'state' and r['round'] == found['round'] and r['frame'] <= found.get('frame', -1) and n <= line]
            context = max(previous, key=lambda item: (item[1]['frame'], item[0])) if previous else None
            return {'reference': reference(sid, current['sources']['recording']['sha256'], line, found),
                    'record': copy.deepcopy(found), 'context': {'line': context[0], 'record': copy.deepcopy(context[1])} if context else None}


def location(ref):
    return None if ref is None else {'line': ref['line'], 'round': ref['round'], 'frame': ref['frame']}


def public(snapshot):
    completed = snapshot['freshness']['completed_rounds']
    focus = snapshot['focus']
    result = {
        'format_version': PUBLIC_FORMAT_VERSION, 'snapshot_id': snapshot['snapshot_id'],
        'session_id': snapshot['session_id'], 'synthetic': snapshot['synthetic'],
        'recording_sha256': snapshot['sources']['recording']['sha256'],
        'freshness': {'latest_completed_round': completed[-1] if completed else None,
                      'latest_recording_round': snapshot['freshness']['latest_recording_round'],
                      'latest_learning_round': snapshot['freshness']['latest_learning_round'],
                      'pending_learning_rounds': list(snapshot['freshness']['pending_learning_rounds']),
                      'learning_ahead_rounds': list(snapshot['freshness']['learning_ahead_rounds'])},
        'quality': snapshot['quality']['state'],
        'metrics': {key: {**{name: metric[name] for name in ('label', 'successes', 'opportunities', 'failures', 'value', 'state', 'estimated', 'evidence_total')},
                          'evidence': [{'opportunity': location(item['opportunity']), 'response': location(item['response']), 'outcome': item['outcome'],
                                        'event': copy.deepcopy(item['event'])} for item in metric['evidence']]}
                    for key, metric in snapshot['metrics'].items()},
        'focus': {'mode': focus['mode'], 'metric': focus['metric'], 'state': focus.get('state'), 'reason': focus['reason'],
                  'action': focus['action'], 'action_reviewed': focus['action'] is not None and focus.get('action_status') == 'reviewed'},
        'habits': {name: {'first_detected_round': row['first_detected_round'], 'first_fixed_round': row['first_fixed_round'],
                          'current_round': row['current']['round'], 'fixed': row['current'].get('fixed'), 'regressed': row['current']['regressed'],
                          'last_regressed_round': max((item['round'] for item in row['history'] if item['regressed']), default=None)}
                   for name, row in sorted(snapshot['learning']['habits'].items())},
        'moments': [{'reference': location(moment['reference']), 'metrics': list(moment['metrics']), 'outcome': moment['outcome'],
                     'response': location(moment['response']), 'event': copy.deepcopy(moment['event']),
                     'metric_outcomes': {key: {'outcome': value['outcome'], 'response': location(value['response'])}
                                         for key, value in moment['metric_outcomes'].items()}} for moment in snapshot['moments']],
        'moments_total': snapshot['moments_total'],
    }
    validate(result, PUBLIC_VALIDATOR, 'public insight snapshot')
    return result


def register(app, data_dir):
    from fastapi import HTTPException

    repository = InsightRepository(data_dir, brain_files_only=True)

    @app.get('/insights/{session_id}')
    def insights(session_id: str, limit: int = PUBLIC_LIMIT):
        if not 1 <= limit <= 50:
            raise HTTPException(422, 'limit must be between 1 and 50')
        try:
            snapshot = repository.snapshot(session_id, limit)
        except ValueError:
            raise HTTPException(422, 'Invalid session id')
        except DataError:
            raise HTTPException(503, 'Insight sources are unavailable, invalid or still changing; retry')
        if snapshot is None:
            raise HTTPException(404, 'Unknown session')
        return public(snapshot)

    return repository


def markdown(snapshot):
    source_kind = 'unknown mode' if snapshot['synthetic'] is None else 'synthetic' if snapshot['synthetic'] else 'recorded'
    lines = [f"# Session insights: {snapshot['session_id']}", '',
             f"Snapshot: `{snapshot['snapshot_id']}`", '',
             f"Source: {source_kind}; completed rounds only; quality: {snapshot['quality']['state']}.", '',
             '| Metric | Successful / opportunities | State |', '| --- | --- | --- |']
    for metric in snapshot['metrics'].values():
        lines.append(f"| {metric['label']} | {metric['successes']}/{metric['opportunities']} | {metric['state']} |")
    lines += ['', f"Focus: {snapshot['focus']['metric'] or snapshot['focus']['reason']}"]
    if snapshot['focus']['action']:
        lines += ['', snapshot['focus']['action']]
    lines += ['', '## Recorded learning', '', '| Habit | First fixed round | Latest fixed |', '| --- | --- | --- |']
    for name, row in sorted(snapshot['learning']['habits'].items()):
        current_fixed = row['current'].get('fixed')
        current_label = 'unavailable' if current_fixed is None else 'fixed' if current_fixed else 'not fixed'
        lines.append(f"| {name} | {row['first_fixed_round'] if row['first_fixed_round'] is not None else 'unavailable'} | {current_label} |")
    accuracy = ', '.join(f"round {r['round']}: " + (f"{r['value']:.2%}" if r['value'] is not None else 'unavailable') for r in snapshot['learning']['prediction_accuracy'])
    evaluation = snapshot['learning']['finetune']
    fine = f"{evaluation['before']:.2%} → {evaluation['after']:.2%}" if all(type(evaluation[key]) in (int, float) for key in ('before', 'after')) else 'unavailable (paired held-out values not supplied)'
    lines += ['', f'Recorded online prediction accuracy: {accuracy or "unavailable"}. Eligible guess counts are unavailable.', '',
              f"Fine-tune comparison: {fine}.", '',
              'Deliberate retests, human improvement and held-out model improvement are not established by this export.', '',
              '## Source-linked moments', '']
    for moment in snapshot['moments']:
        ref = moment['reference']
        lines.append(f"- Round {ref['round']}, frame {ref['frame']}, recording line {ref['line']}: {moment['event']['kind']} ({moment['outcome']}).")
    lines += ['', f"Showing {len(snapshot['moments'])} of {snapshot['moments_total']} candidate moments.", '',
              'Source fingerprints:', '']
    lines.extend(f"- {key}: {value['sha256'] or 'unavailable'}; complete bytes {value['consumed_bytes']}; pending tail {value['pending_tail']}." for key, value in snapshot['sources'].items())
    return '\n'.join(lines) + '\n'


def write_export(snapshot, directory):
    check_id(snapshot['session_id'])
    validate(snapshot, SNAPSHOT_VALIDATOR, 'internal insight export')
    directory = Path(directory).resolve()
    if directory.is_relative_to((ROOT / 'data/samples').resolve()):
        raise ValueError('Choose an output directory outside checked-in sample bundles, such as ./data/analytics')
    directory.mkdir(parents=True, exist_ok=True)
    values = {'.json': encoded(snapshot) + b'\n', '.md': markdown(snapshot).encode('utf-8')}
    staged = []
    try:
        for extension, content in values.items():
            target = directory / f"{snapshot['session_id']}{extension}"
            if target.is_symlink():
                raise ValueError('Export target must not be a symlink')
            with tempfile.NamedTemporaryFile(dir=directory, prefix='.insights-', delete=False) as stream:
                staged.append((Path(stream.name), target))
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        for temporary, target in staged:
            os.replace(temporary, target)
    finally:
        for temporary, target in staged:
            temporary.unlink(missing_ok=True)
    return [str(target) for temporary, target in staged]


def main(argv=None):
    parser = argparse.ArgumentParser(description='Export internal, source-linked completed-round analytics; no cloud or telemetry initialization')
    parser.add_argument('session_id')
    parser.add_argument('--data-dir', default=os.environ.get('DATA_DIR', './data'))
    parser.add_argument('--output-dir')
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--focus', choices=METRIC_ORDER)
    parser.add_argument('--public', action='store_true', help='print the proposed public v1 JSON instead of writing exports')
    args = parser.parse_args(argv)
    try:
        snapshot = InsightRepository(args.data_dir).snapshot(args.session_id, args.limit, args.focus)
        if snapshot is None:
            parser.exit(1, 'Unknown session\n')
        if args.public:
            print(json.dumps(public(snapshot), indent=2, sort_keys=True, ensure_ascii=False))
            return
        paths = write_export(snapshot, args.output_dir or Path(args.data_dir) / 'analytics')
    except (DataError, ValueError, OSError):
        parser.exit(1, 'Cannot export insights: invalid/unavailable input or output; check the session, source files and output directory\n')
    print(markdown(snapshot), end='')
    print('Wrote JSON and Markdown:', *paths, sep='\n')


if __name__ == '__main__':
    main()
