# B8: session Parquet archive

## Implementation plan

1. Add a standalone `python -m analytics.archive` command. Read `--data-dir`, then `DATA_DIR`, then `./data`; write one `<session_id>.parquet` per recording to `DATA_DIR/archive` (or `--output-dir`). Keep conversion outside the live analytics service.
2. Discover canonical session metadata and recordings, paired samples and zipped samples, including the checked-in synthetic fixture. Prefer canonical recordings over sample copies; reject ambiguous duplicates within one tier. Read ZIP members directly without extracting them or importing `game/`.
3. Stream JSONL into bounded PyArrow row groups with Zstandard compression. Use a fixed envelope (`session_id`, `t`, `round`, `frame`, `source_line`, `record_json`) so heterogeneous records and future fields cannot disappear through inferred schemas. Preserve the full JSON object as text, including unknown record types. This is a recording archive, not a reducer or a training feature table.
4. Ignore blank lines and tolerate an incomplete final line without a newline. Accept complete final objects without a newline. Fail on malformed complete lines, non-object records, mismatched/unsafe session IDs or invalid envelope types. Preserve record order and round-relative frames exactly; do not infer missing frames or merge separate learning files.
5. Write each archive to a temporary file beside its destination, check that the source has not changed, verify the Parquet row count, then replace atomically. Keep existing archives on failure, clean up temporary files, report failures per source and return a nonzero exit code. Reruns replace snapshots rather than append duplicates. Record source, source SHA-256, session metadata, row count and incomplete-tail status in the Parquet footer.
6. Put PyArrow and DuckDB in `analytics/requirements-archive.txt`. PyArrow alone writes the files; DuckDB is for SQL verification. Polars adds no necessary functionality here. The analytics server keeps its existing dependencies.
7. Verify round-trip preservation, SQL across mixed records/sessions, ZIP and canonical discovery, empty inputs, reruns, truncated tails, invalid input and failed-write preservation. Run the analytics suite and frozen contract validator, then convert the repository's recordings and compare every archive count with its source.

The optional Spaces backup is a documented manual `rclone copy` step using an existing configured remote. The archive command never uploads data or reads cloud credentials. JSONL and ZIP sources remain the source of truth. PR integration and deployment are separate from this batch.

## Run

```sh
.venv/bin/python -m pip install -r analytics/requirements-archive.txt
.venv/bin/python -m analytics.archive --data-dir ./data
```

The command prints each session's row count and output path, followed by archived/failed totals. Empty discovery succeeds with zero sessions. Archive files are local and already excluded from Git by `data/*`.

Discovery reads `sessions/*.json`, `recordings/*.jsonl` and recursive samples, including nested synthetic datasets. Canonical metadata recording references resolve relative to the repository root, as in the analytics service. Sample metadata is paired by filename; without metadata the first record's session ID is used, falling back to the filename for empty files. Precedence is canonical metadata, canonical recordings without metadata, plain samples, then ZIP samples. Conflicting sources at the same precedence fail that session. Learning directories and `*.learning.jsonl` members are excluded. ZIP member paths are never extracted.

## Storage and SQL

Each nonblank, complete JSON object becomes one row. `source_line` is the one-based physical JSONL line number. `round` and `frame` are nullable signed 64-bit integers; they retain the producer's round/frame values. `record_json` retains the original JSON text (excluding the line ending), including nested objects, arrays and unknown fields. Unknown types remain available as opaque rows and have no special interpretation.

Query all sessions with the DuckDB Python package; its installation does not require a separate `duckdb` executable:

```sh
.venv/bin/python -c "import duckdb; print(duckdb.sql(\"SELECT session_id, t, count(*) AS rows FROM read_parquet('data/archive/*.parquet') GROUP BY session_id, t ORDER BY session_id, t\"))"
.venv/bin/python -c "import duckdb; print(duckdb.sql(\"SELECT session_id, round, frame, json_extract(record_json, '$.players[0].health') AS slot_0_health FROM read_parquet('data/archive/*.parquet') WHERE t = 'state' LIMIT 5\"))"
```

The default glob requires at least one archive. Counts match complete nonblank source objects, excluding an incomplete tail; duplicate copies of a session are archived once. Separate `learning/*.jsonl` files are not part of recording counts. A successful archive of an active recording is a snapshot, and the command reports if it omitted an incomplete tail. Run it again after recording stops for a complete snapshot.

PyArrow supports incremental writes with `ParquetWriter` ([Arrow documentation](https://arrow.apache.org/docs/python/parquet/parquet.html)); DuckDB queries Parquet files and globs directly ([DuckDB documentation](https://duckdb.org/docs/stable/data/parquet/overview)).

## Optional backup

After configuring a Spaces remote through `rclone config`, substitute the real remote and bucket:

```sh
rclone copy ./data/archive spaces:YOUR_BUCKET/kumite/archive --dry-run
rclone copy ./data/archive spaces:YOUR_BUCKET/kumite/archive
```

This copies archives without deleting remote objects. No upload is part of local conversion or verification.

## Verify

```sh
.venv/bin/python -m unittest discover -s analytics/tests -p test_archive.py -v
.venv/bin/python -m unittest discover -s analytics/tests
.venv/bin/python contracts/validate.py
```

## Retained local verification (2026-10-17)

Implemented the plan above using PyArrow 26.0.0 and DuckDB 1.5.6. All 16 archive tests passed, including truncated UTF-8 tails, failed publication and changed-source protection. The complete analytics suite ran 89 tests successfully with one opt-in database test skipped. Frozen contract validation passed. The local conversion and a repeat conversion both reported four sessions and zero failures:

| Session | Source objects / Parquet rows |
|---|---:|
| `2026-10-17T13-05-00_synth_djin_vs_kaz` | 5,519 |
| `2026-10-17T21-13-10_sahil_djin_vs_kaz` | 593 |
| `2026-10-17T23-48-17_sahil_djin_vs_kaz` | 15,694 |
| `2026-10-18T01-24-57_sahil_djin_vs_kaz` | 12,802 |
| Total | 34,608 |

An independent source-to-archive comparison decoded every original object and every `record_json` value and found identical contents in order. DuckDB's count across all four archives was 34,608. Archives totalled 1,843,534 bytes; this is a measured artifact size, not an estimate for future sessions. The two versus inputs were read from ZIPs. No Spaces backup was run.
