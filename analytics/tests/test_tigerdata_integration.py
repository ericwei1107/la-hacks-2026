import json
import os
import shutil
import tempfile
import unittest
import uuid
from dataclasses import replace
from pathlib import Path

from analytics.tigerdata.__main__ import import_once
from analytics.tigerdata.database import Database, DatabaseError, connection
from analytics.repository import FileRepository
from analytics.tigerdata.repository import TigerRepository
from analytics.tigerdata.trends import signature
from unittest.mock import patch

from analytics.tigerdata.source import ROOT, Row, discover, prepare


@unittest.skipUnless(os.environ.get('TIGERDATA_RUN_INTEGRATION') == '1' and os.environ.get('DATABASE_URL'), 'Live Tiger Data verification requires DATABASE_URL and TIGERDATA_RUN_INTEGRATION=1')
class TigerDataIntegrationTest(unittest.TestCase):
    def test_real_hypertables_backfill_replacement_rollback_and_reconnect(self):
        from psycopg import sql

        url = os.environ['DATABASE_URL']
        schema = 'kumite_test_' + uuid.uuid4().hex
        conn = connection(url)
        try:
            db = Database(conn, schema=schema)
            db.initialize()
            db.initialize()
            count = conn.execute('SELECT count(*) FROM timescaledb_information.hypertables WHERE hypertable_schema=%s', (schema,)).fetchone()[0]
            self.assertEqual(count, 4)
            self.assertEqual(conn.execute('SELECT count(*) FROM timescaledb_information.continuous_aggregates WHERE view_schema=%s AND view_name=%s', (schema, 'session_trends')).fetchone()[0], 1)
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                samples = root / 'samples'
                samples.mkdir()
                for path in (ROOT / 'tools/mock/tests/fixtures').glob('two-rounds*'):
                    shutil.copy(path, samples / path.name)
                self.assertEqual(import_once(root, db), (2, 0, 0))
                discovered = discover(root)
                sid, (meta, path) = next(iter(discovered.items()))
                batches = prepare(meta, path, root)
                for table in ('frames', 'events', 'round_metrics'):
                    expected = sum(len(batch.rows[table]) for batch in batches)
                    actual = conn.execute(sql.SQL('SELECT count(*) FROM {}').format(db.table(table))).fetchone()[0]
                    self.assertEqual(actual, expected)
                self.assertEqual(import_once(root, db), (0, 2, 0))
                files = FileRepository(root)
                expected = files.trends(meta['player'], meta['human_character'])
                stored = db.trends([sid])
                self.assertEqual(stored[sid][0], signature(files, meta, path))
                self.assertEqual(stored[sid][1], expected['series'][0]['values'])
                hybrid = TigerRepository(root, url)
                with patch('analytics.tigerdata.repository.Database', side_effect=lambda connection: Database(connection, schema)), patch('analytics.tigerdata.repository.trend_values', side_effect=AssertionError('File reducer used')):
                    self.assertEqual(hybrid.trends(meta['player'], meta['human_character']), expected)
                with patch('analytics.tigerdata.repository.connection', side_effect=DatabaseError('Connection failed')), self.assertLogs('analytics.tigerdata', level='WARNING'):
                    self.assertEqual(hybrid.trends(meta['player'], meta['human_character']), expected)
                records = [json.loads(line) for line in path.read_text().splitlines()]
                event = next(record for record in records if record['t'] == 'event' and record['round'] == 1)
                event['correction_test'] = True
                event.update(kind='counter_hit', actor=meta['human_slot'], target=1-meta['human_slot'], damage=12)
                path.write_text(''.join(json.dumps(record) + '\n' for record in records))
                self.assertEqual(import_once(root, db), (1, 1, 0))
                self.assertEqual(db.trends([sid])[sid][1], files.trends(meta['player'], meta['human_character'])['series'][0]['values'])
                (root / 'learning').mkdir()
                (root / 'learning' / f'{sid}.jsonl').write_text(json.dumps({'t': 'learning_round', 'round': 1, 'session_id': sid, 'prediction_accuracy': 0.99, 'habits': {'low_defense': {'n': 4, 'p': 0.8, 'mastery': 0.9, 'fixed': True}}}) + '\n')
                self.assertEqual(import_once(root, db), (1, 1, 0))
                values = db.trends([sid])[sid][1]
                self.assertEqual(values['habit_probability:low_defense'], 0.8)
                self.assertEqual(values['time_to_mastery:low_defense'], 1)
                self.assertEqual(values, files.trends(meta['player'], meta['human_character'])['series'][0]['values'])
                original = conn.execute(sql.SQL('SELECT fingerprint FROM {} WHERE session_id=%s AND round=1').format(db.table('ingest_rounds')), (sid,)).fetchone()[0]
                frames = conn.execute(sql.SQL('SELECT count(*) FROM {}').format(db.table('frames'))).fetchone()[0]
                conn.execute(sql.SQL("ALTER TABLE {} ADD CONSTRAINT reject_test CHECK (NOT (payload ? 'reject_test'))").format(db.table('frames')))
                batch = prepare(meta, path, root)[0]
                rows = {key: list(value) for key, value in batch.rows.items()}
                row = rows['frames'][0]
                rows['frames'][0] = Row(row.observed_at, row.source, row.source_line, {**row.record, 'reject_test': True})
                with self.assertRaises(DatabaseError):
                    db.ingest(replace(batch, fingerprint='rejected', rows=rows))
                self.assertEqual(conn.execute(sql.SQL('SELECT count(*) FROM {}').format(db.table('frames'))).fetchone()[0], frames)
                self.assertEqual(conn.execute(sql.SQL('SELECT fingerprint FROM {} WHERE session_id=%s AND round=1').format(db.table('ingest_rounds')), (sid,)).fetchone()[0], original)
                conn.close()
                with self.assertRaises(DatabaseError):
                    db.ingest(batch)
                conn = connection(url)
                db = Database(conn, schema=schema)
                self.assertEqual(import_once(root, db), (0, 2, 0))
        finally:
            if conn.closed:
                conn = connection(url)
            try:
                conn.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
            finally:
                conn.close()


if __name__ == '__main__':
    unittest.main()
