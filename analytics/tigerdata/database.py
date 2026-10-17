from datetime import datetime, timedelta, timezone
import math
from pathlib import Path

TABLES = ('frames', 'events', 'round_metrics')


class DatabaseError(Exception):
    pass


def connection(url):
    try:
        import psycopg
    except ImportError:
        raise DatabaseError('Install analytics/tigerdata/requirements.txt before using database commands') from None
    try:
        return psycopg.connect(url, autocommit=True, connect_timeout=5, options='-c statement_timeout=15000 -c lock_timeout=5000')
    except Exception:
        raise DatabaseError('Database connection failed; check DATABASE_URL and network access') from None


class Database:
    def __init__(self, conn, schema='kumite'):
        from psycopg import sql
        from psycopg.types.json import Jsonb

        self.conn = conn
        self.schema = schema
        self.sql = sql
        self.jsonb = Jsonb

    def table(self, name):
        return self.sql.Identifier(self.schema, name)

    def initialize(self):
        try:
            with self.conn.transaction():
                version = self.conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'").fetchone()
                if not version or tuple(int(part) for part in version[0].split('.')[:2]) < (2, 13):
                    raise DatabaseError('TimescaleDB 2.13 or later must be enabled on the target database')
                script = Path(__file__).with_name('schema.sql').read_text()
                self.conn.execute(self.sql.SQL(script).format(schema=self.sql.Identifier(self.schema)))
                for name in (*TABLES, 'trend_snapshots'):
                    qualified = self.table(name).as_string(self.conn)
                    self.conn.execute("SELECT create_hypertable(%s::regclass, by_range('observed_at'), if_not_exists => TRUE)", (qualified,))
                self.conn.execute(self.sql.SQL("CREATE MATERIALIZED VIEW IF NOT EXISTS {} WITH (timescaledb.continuous, timescaledb.materialized_only=true) AS SELECT time_bucket(INTERVAL '1 day', observed_at) AS bucket, session_id, metric, last(value, observed_at) AS value FROM {} GROUP BY bucket, session_id, metric WITH NO DATA").format(self.table('session_trends'), self.table('trend_snapshots')))
        except DatabaseError:
            raise
        except Exception:
            raise DatabaseError('Schema initialization failed; verify database permissions and TimescaleDB support') from None

    def ingest(self, batch):
        meta = batch.meta
        sid = meta['session_id']
        try:
            with self.conn.transaction():
                self.conn.execute(self.sql.SQL('INSERT INTO {} (session_id, started_at, payload) VALUES (%s, %s, %s) ON CONFLICT (session_id) DO UPDATE SET started_at=EXCLUDED.started_at, payload=EXCLUDED.payload').format(self.table('sessions')), (sid, datetime.fromisoformat(meta['started_at'].replace('Z', '+00:00')), self.jsonb(meta)))
                previous = self.conn.execute(self.sql.SQL('SELECT fingerprint FROM {} WHERE session_id=%s AND round=%s').format(self.table('ingest_rounds')), (sid, batch.number)).fetchone()
                if previous and previous[0] == batch.fingerprint:
                    return False
                with self.conn.cursor() as cursor:
                    for table in TABLES:
                        cursor.execute(self.sql.SQL('DELETE FROM {} WHERE session_id=%s AND round=%s').format(self.table(table)), (sid, batch.number))
                        rows = [(row.observed_at, sid, batch.number, row.record.get('frame') if row.record['t'] != 'learning_round' else None, meta['player'], meta['human_character'], meta['difficulty'], row.source, row.source_line, row.record['t'], self.jsonb(row.record)) for row in batch.rows[table]]
                        if rows:
                            cursor.executemany(self.sql.SQL('INSERT INTO {} (observed_at,session_id,round,frame,player,character,difficulty,source,source_line,kind,payload) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)').format(self.table(table)), rows)
                self.conn.execute(self.sql.SQL('INSERT INTO {} (session_id,round,fingerprint) VALUES (%s,%s,%s) ON CONFLICT (session_id,round) DO UPDATE SET fingerprint=EXCLUDED.fingerprint, imported_at=now()').format(self.table('ingest_rounds')), (sid, batch.number, batch.fingerprint))
            return True
        except Exception:
            raise DatabaseError(f'Round import failed for session {sid}, round {batch.number}; transaction rolled back') from None

    def publish(self, snapshot):
        if not snapshot.rows:
            return
        sid = snapshot.meta['session_id']
        locked = False
        try:
            self.conn.execute('SELECT pg_advisory_lock(hashtext(%s), hashtext(%s))', (self.schema, sid))
            locked = True
            previous = self.conn.execute(self.sql.SQL('SELECT signature, ready, first_bucket, last_bucket FROM {} WHERE session_id=%s').format(self.table('trend_imports')), (sid,)).fetchone()
            if previous and previous[0] == snapshot.signature and previous[1] == snapshot.eligible:
                return
            moments = [row[0] for row in snapshot.rows]
            first = min(moments).astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            last = max(moments).astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            if previous:
                first, last = min(first, previous[2]), max(last, previous[3])
            latest_round = max(row[2] for row in snapshot.rows)
            count = sum(row[2] == latest_round for row in snapshot.rows)
            with self.conn.transaction():
                self.conn.execute(self.sql.SQL('DELETE FROM {} WHERE session_id=%s').format(self.table('trend_snapshots')), (sid,))
                with self.conn.cursor() as cursor:
                    cursor.executemany(self.sql.SQL('INSERT INTO {} (observed_at,session_id,round,metric,value) VALUES (%s,%s,%s,%s,%s)').format(self.table('trend_snapshots')), snapshot.rows)
                self.conn.execute(self.sql.SQL('INSERT INTO {} (session_id,signature,ready,metric_count,first_bucket,last_bucket) VALUES (%s,%s,FALSE,%s,%s,%s) ON CONFLICT (session_id) DO UPDATE SET signature=EXCLUDED.signature,ready=FALSE,metric_count=EXCLUDED.metric_count,first_bucket=EXCLUDED.first_bucket,last_bucket=EXCLUDED.last_bucket').format(self.table('trend_imports')), (sid, snapshot.signature, count, first, last))
            self.conn.execute('CALL refresh_continuous_aggregate(%s::regclass, %s::timestamptz, %s::timestamptz)', (self.table('session_trends').as_string(), first, last))
            if snapshot.eligible:
                self.conn.execute(self.sql.SQL('UPDATE {} SET ready=TRUE WHERE session_id=%s AND signature=%s').format(self.table('trend_imports')), (sid, snapshot.signature))
        except Exception:
            raise DatabaseError(f'Trend publication failed for session {sid}; files remain available') from None
        finally:
            if locked:
                try:
                    self.conn.execute('SELECT pg_advisory_unlock(hashtext(%s), hashtext(%s))', (self.schema, sid))
                except Exception:
                    pass

    def trends(self, session_ids):
        try:
            rows = self.conn.execute(self.sql.SQL('SELECT i.session_id,i.signature,i.metric_count,v.metric,v.value FROM {} i JOIN LATERAL (SELECT DISTINCT ON (metric) metric,value FROM {} WHERE session_id=i.session_id ORDER BY metric,bucket DESC) v ON TRUE WHERE i.ready AND i.session_id=ANY(%s)').format(self.table('trend_imports'), self.table('session_trends')), (session_ids,)).fetchall()
            result = {}
            counts = {}
            for sid, signature, count, metric, value in rows:
                if value is not None and not math.isfinite(value):
                    raise ValueError('Invalid aggregate value')
                result.setdefault(sid, (signature, {}))[1][metric] = value
                counts[sid] = count
            return {sid: value for sid, value in result.items() if len(value[1]) == counts[sid]}
        except Exception:
            raise DatabaseError('Trend query failed; verify explicit schema initialization') from None
