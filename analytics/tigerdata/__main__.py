import argparse
import json
import logging
import os
import time

from analytics.tigerdata.database import Database, DatabaseError, connection
from analytics.repository import DataError
from analytics.tigerdata.trends import signature, snapshot
from analytics.repository import FileRepository
from analytics.tigerdata.source import InputError, discover, prepare

logger = logging.getLogger('analytics.tigerdata')


def selected_sessions(data_dir, session_ids=None):
    errors = {}
    sessions = discover(data_dir, errors)
    if session_ids:
        missing = set(session_ids) - sessions.keys()
        if missing:
            raise InputError('Requested session unavailable: ' + ', '.join(sorted(missing)))
        sessions = {sid: entry for sid, entry in sessions.items() if sid in session_ids}
        errors = {sid: error for sid, error in errors.items() if sid in session_ids}
    return sessions, errors


def plan(data_dir, session_ids=None):
    """Prepare desired values locally. Never construct a database connection."""
    from analytics.stats import CALCULATION_VERSION

    sessions, errors = selected_sessions(data_dir, session_ids)
    if errors:
        raise InputError('Invalid session metadata in plan scope')
    output = []
    for sid, (meta, recording) in sorted(sessions.items()):
        initial = signature(FileRepository(data_dir), meta, recording)
        batches = prepare(meta, recording, data_dir)
        derived = snapshot(data_dir, meta, recording, batches)
        if initial != derived.signature:
            raise DataError(f'{sid}: source changed during plan preparation; retry')
        last_round = max((batch.number for batch in batches), default=None)
        output.append({'session_id': sid, 'signature': derived.signature,
                       'eligible': derived.eligible, 'snapshot_rows': len(derived.rows),
                       'final_punish_rate': next((row[4] for row in derived.rows
                                                 if row[2] == last_round and row[3] == 'punish_rate'), None),
                       'rounds': [{'round': batch.number, 'fingerprint': batch.fingerprint,
                                   'rows': {name: len(rows) for name, rows in batch.rows.items()},
                                   'punish_rate': next(row.record['punish_rate'] for row in batch.rows['round_metrics']
                                                       if row.source == 'calculated')}
                                  for batch in batches]})
    return {'calculation_version': CALCULATION_VERSION, 'cloud_checked': False,
            'cloud_writes': False, 'sessions': output}


def import_once(data_dir, database, session_ids=None):
    sessions, errors = selected_sessions(data_dir, session_ids)
    imported = skipped = 0
    failures = len(errors)
    for sid, (meta, recording) in sessions.items():
        try:
            initial = signature(FileRepository(data_dir), meta, recording)
            batches = prepare(meta, recording, data_dir)
            derived = snapshot(data_dir, meta, recording, batches)
            if initial != derived.signature:
                raise DataError(f"{sid}: source changed during round preparation; retry")
        except (InputError, DataError) as exc:
            logger.warning('Session %s skipped: %s', sid, exc)
            failures += 1
            continue
        for batch in batches:
            if database.ingest(batch):
                imported += 1
            else:
                skipped += 1
        database.publish(derived)
    return imported, skipped, failures


def main(argv=None):
    parser = argparse.ArgumentParser(description='Standalone completed-round ingestion for Tiger Data')
    parser.add_argument('command', choices=('init', 'plan', 'backfill', 'watch'))
    parser.add_argument('--data-dir', default=os.environ.get('DATA_DIR', './data'))
    parser.add_argument('--session-id', action='append', help='limit plan/backfill/watch to these exact IDs; repeatable')
    args = parser.parse_args(argv)
    if args.command == 'init' and args.session_id:
        parser.error('--session-id cannot scope schema initialization')
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    if args.command == 'plan':
        try:
            print(json.dumps(plan(args.data_dir, args.session_id), indent=2, sort_keys=True))
            return 0
        except (InputError, DataError) as exc:
            logger.error('%s', exc)
            return 1
    url = os.environ.get('DATABASE_URL')
    if not url:
        logger.error('DATABASE_URL is required; set it in the environment')
        return 2
    while True:
        try:
            with connection(url) as conn:
                database = Database(conn)
                if args.command == 'init':
                    database.initialize()
                    logger.info('Schema initialized: kumite sessions, checkpoints and four hypertables plus the trend aggregate')
                    return 0
                imported, skipped, failures = import_once(args.data_dir, database, args.session_id)
                logger.info('Rounds imported=%s unchanged=%s invalid_sessions=%s', imported, skipped, failures)
                if args.command == 'backfill':
                    return 1 if failures else 0
        except (DatabaseError, InputError) as exc:
            logger.warning('%s', exc)
            if args.command != 'watch':
                return 1
        except Exception:
            logger.warning('Database operation failed; credentials and driver error details omitted')
            if args.command != 'watch':
                return 1
        if args.command != 'watch':
            return 0
        time.sleep(2)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
