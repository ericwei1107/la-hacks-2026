CREATE SCHEMA IF NOT EXISTS {schema};
CREATE TABLE IF NOT EXISTS {schema}.sessions (
    session_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS {schema}.ingest_rounds (
    session_id TEXT NOT NULL,
    round INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, round)
);
CREATE TABLE IF NOT EXISTS {schema}.frames (
    observed_at TIMESTAMPTZ NOT NULL,
    session_id TEXT NOT NULL,
    round INTEGER NOT NULL,
    frame INTEGER,
    player TEXT NOT NULL,
    character TEXT NOT NULL,
    difficulty INTEGER NOT NULL,
    source TEXT NOT NULL,
    source_line BIGINT NOT NULL,
    kind TEXT NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (observed_at, session_id, round, source, source_line)
);
CREATE TABLE IF NOT EXISTS {schema}.events (LIKE {schema}.frames INCLUDING ALL);
CREATE TABLE IF NOT EXISTS {schema}.round_metrics (LIKE {schema}.frames INCLUDING ALL);
CREATE INDEX IF NOT EXISTS frames_session_round ON {schema}.frames (session_id, round);
CREATE INDEX IF NOT EXISTS events_session_round ON {schema}.events (session_id, round);
CREATE INDEX IF NOT EXISTS round_metrics_session_round ON {schema}.round_metrics (session_id, round);
CREATE TABLE IF NOT EXISTS {schema}.trend_snapshots (
    observed_at TIMESTAMPTZ NOT NULL,
    session_id TEXT NOT NULL,
    round INTEGER NOT NULL,
    metric TEXT NOT NULL,
    value DOUBLE PRECISION,
    PRIMARY KEY (observed_at, session_id, round, metric)
);
CREATE INDEX IF NOT EXISTS trend_snapshots_session ON {schema}.trend_snapshots (session_id);
CREATE TABLE IF NOT EXISTS {schema}.trend_imports (
    session_id TEXT PRIMARY KEY,
    signature TEXT NOT NULL,
    ready BOOLEAN NOT NULL DEFAULT FALSE,
    metric_count INTEGER NOT NULL,
    first_bucket TIMESTAMPTZ NOT NULL,
    last_bucket TIMESTAMPTZ NOT NULL
);
