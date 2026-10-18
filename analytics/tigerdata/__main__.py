import argparse
import logging
import os
import time

from analytics.tigerdata.database import Database, DatabaseError, connection
from analytics.repository import DataError
from analytics.tigerdata.trends import signature, snapshot
from analytics.repository import FileRepository
from analytics.tigerdata.source import InputError, discover, prepare

logger = logging.getLogger('analytics.tigerdata')


def import_once(data_dir, database):
    imported = skipped = failures = 0
    for sid, (meta, recording) in discover(data_dir).items():
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
    parser.add_argument('command', choices=('init', 'backfill', 'watch'))
    parser.add_argument('--data-dir', default=os.environ.get('DATA_DIR', './data'))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
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
                imported, skipped, failures = import_once(args.data_dir, database)
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
