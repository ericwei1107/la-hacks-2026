import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from analytics.archive import ArchiveError, Source, archive_source, discover, main
from analytics.repository import ROOT

try:
    import duckdb
    import pyarrow.parquet as pq
except ImportError:
    duckdb = pq = None


@unittest.skipUnless(duckdb and pq, 'install analytics/requirements-archive.txt')
class ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.output = self.root / 'archive'

    def recording(self, sid='session', records=None, directory='recordings'):
        path = self.root / directory / f'{sid}.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        records = records if records is not None else [{'t': 'event', 'session_id': sid, 'round': 1, 'frame': 10, 'kind': 'hit'}]
        path.write_text(''.join(json.dumps(record, ensure_ascii=False) + '\n' for record in records), encoding='utf-8')
        return Source(path, sid=sid)

    def meta(self, sid, path):
        meta = json.loads((ROOT / 'contracts/examples/session.json').read_text())
        meta.update(session_id=sid, recording=str(path))
        return meta

    def invoke(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_round_trip_mixed_records_nested_fields_and_exact_frames(self):
        records = [
            {'t': 'state', 'session_id': 'session', 'round': 1, 'frame': 4375, 'players': [{'health': 170}, {'health': 150}], 'future': {'emoji': '拳', 'list': [1, None, True]}},
            {'t': 'tactical', 'session_id': 'session', 'round': 1, 'frame': 4380, 'probabilities': [0.2, 0.8]},
            {'t': 'plan', 'session_id': 'session', 'round': 2, 'frame': 0, 'weights': {'throw': 0.7}},
            {'t': 'round_summary', 'session_id': 'session', 'round': 2, 'winner': 0},
            {'t': 'future_kind', 'session_id': 'session', 'round': 2, 'opaque': {'n': 2**80}},
        ]
        source = self.recording(records=records)
        path, count, truncated = archive_source(source, self.output, batch_size=2)
        table = pq.read_table(path)
        self.assertEqual(count, len(records))
        self.assertFalse(truncated)
        self.assertEqual([json.loads(text) for text in table['record_json'].to_pylist()], records)
        self.assertEqual(table['frame'].to_pylist(), [4375, 4380, 0, None, None])
        self.assertEqual(pq.read_metadata(path).num_row_groups, 3)
        footer = pq.read_metadata(path).metadata
        self.assertEqual(footer[b'kumite.source_sha256'].decode(), hashlib.sha256(source.path.read_bytes()).hexdigest())
        self.assertEqual(footer[b'kumite.rows'], b'5')

    def test_duckdb_queries_multiple_sessions_and_json_payloads(self):
        for sid in ('one', 'two'):
            archive_source(self.recording(sid, [{'t': 'state', 'session_id': sid, 'round': 1, 'frame': 0, 'players': [{'health': 170}]}]), self.output)
        with duckdb.connect() as db:
            result = db.execute('SELECT count(*), sum(CAST(json_extract(record_json, \'$.players[0].health\') AS INTEGER)) FROM read_parquet(?)', [str(self.output / '*.parquet')]).fetchone()
        self.assertEqual(result, (2, 340))

    def test_blank_lines_crlf_complete_last_line_and_physical_line_numbers(self):
        source = self.recording()
        text = '  ' + json.dumps({'t': 'event', 'session_id': 'session', 'round': 1, 'frame': 3}) + '  '
        source.path.write_bytes(b'\r\n' + text.encode() + b'\r\n\n' + text.encode())
        path, count, truncated = archive_source(source, self.output)
        rows = pq.read_table(path).to_pylist()
        self.assertEqual((count, truncated), (2, False))
        self.assertEqual([record['source_line'] for record in rows], [2, 4])
        self.assertEqual([record['record_json'] for record in rows], [text, text])

    def test_truncated_tail_snapshot_then_completion_on_rerun(self):
        source = self.recording()
        complete = source.path.read_bytes()
        source.path.write_bytes(complete + b'{"t":"event","session_id":')
        path, count, truncated = archive_source(source, self.output)
        self.assertEqual((count, truncated), (1, True))
        self.assertEqual(pq.read_metadata(path).metadata[b'kumite.incomplete_tail'], b'true')
        source.path.write_bytes(complete + complete)
        archive_source(source, self.output)
        archive_source(source, self.output)
        self.assertEqual(pq.read_metadata(path).num_rows, 2)
        self.assertEqual(len(list(self.output.glob('*.parquet'))), 1)

    def test_invalid_records_preserve_previous_archive(self):
        source = self.recording()
        path, _, _ = archive_source(source, self.output)
        previous = path.read_bytes()
        cases = [b'garbage', b'{"t":\n', b'[]\n', b'{"session_id":"other"}\n', b'{"frame":true}\n', b'{"round":1.5}\n', b'{"frame":9223372036854775808}\n', b'{"t":1}\n', b'{"value":NaN}\n', b'\xff\n']
        for raw in cases:
            with self.subTest(raw=raw):
                source.path.write_bytes(raw)
                with self.assertRaises((ValueError, ArchiveError)):
                    archive_source(source, self.output)
                self.assertEqual(path.read_bytes(), previous)
                self.assertEqual(list(self.output.glob('*.tmp')), [])

    def test_utf8_character_cut_off_at_end_is_a_truncated_tail(self):
        source = self.recording()
        with source.path.open('ab') as stream:
            stream.write(b'{"text":"\xe6\x8b')
        path, count, truncated = archive_source(source, self.output)
        self.assertEqual((count, truncated), (1, True))
        self.assertEqual(pq.read_metadata(path).num_rows, 1)

    def test_changed_source_or_publish_failure_keeps_previous_archive(self):
        source = self.recording()
        path, _, _ = archive_source(source, self.output)
        previous = path.read_bytes()
        with patch('analytics.archive.stamp', side_effect=[(1,), (2,)]):
            with self.assertRaisesRegex(ArchiveError, 'source changed'):
                archive_source(source, self.output)
        with patch('analytics.archive.os.replace', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                archive_source(source, self.output)
        self.assertEqual(path.read_bytes(), previous)
        self.assertEqual(list(self.output.glob('*.tmp')), [])

    def test_empty_recording_and_empty_discovery(self):
        code, stdout, stderr = self.invoke('--data-dir', str(self.root))
        self.assertEqual((code, stderr), (0, ''))
        self.assertIn('archived=0 failed=0', stdout)
        source = self.recording(records=[])
        path, count, truncated = archive_source(source, self.output)
        self.assertEqual((count, truncated), (0, False))
        self.assertEqual(pq.read_metadata(path).num_rows, 0)
        self.assertEqual(discover(self.root)[0][0].sid, 'session')

    def test_canonical_metadata_recording_reference_and_sample_precedence(self):
        canonical = self.recording()
        sessions = self.root / 'sessions'
        sessions.mkdir()
        meta = self.meta('session', canonical.path)
        (sessions / 'session.json').write_text(json.dumps(meta))
        self.recording(directory='samples')
        sources, errors = discover(self.root)
        self.assertEqual(errors, [])
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].path, canonical.path)
        path, _, _ = archive_source(sources[0], self.output)
        self.assertEqual(json.loads(pq.read_metadata(path).metadata[b'kumite.session_metadata']), meta)

    def test_paired_sample_uses_metadata_id_not_filename(self):
        source = self.recording('session', directory='samples')
        renamed = source.path.with_name('sample.jsonl')
        source.path.rename(renamed)
        renamed.with_suffix('.session.json').write_text(json.dumps(self.meta('session', renamed)))
        sources, errors = discover(self.root)
        self.assertEqual(errors, [])
        self.assertEqual(sources[0].sid, 'session')

    def test_zip_members_are_read_without_extraction_and_learning_is_excluded(self):
        samples = self.root / 'samples'
        samples.mkdir()
        path = samples / 'versus.zip'
        record = {'t': 'event', 'session_id': 'zip-session', 'round': 1, 'frame': 9}
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('nested/versus.jsonl', json.dumps(record) + '\n')
            archive.writestr('nested/versus.session.json', json.dumps(self.meta('zip-session', Path('unused'))))
            archive.writestr('learning/zip-session.jsonl', '{bad learning file}')
        sources, errors = discover(self.root)
        self.assertEqual(errors, [])
        self.assertEqual(len(sources), 1)
        result, count, _ = archive_source(sources[0], self.output)
        self.assertEqual((result.stem, count), ('zip-session', 1))
        self.assertEqual([json.loads(row['record_json']) for row in pq.read_table(result).to_pylist()], [record])
        self.assertEqual(list(samples.iterdir()), [path])

    def test_nested_synthetic_dataset_excludes_learning_files(self):
        source = self.recording('synthetic', directory='samples/synthetic/recordings')
        sessions = source.path.parent.parent / 'sessions'
        sessions.mkdir()
        (sessions / 'synthetic.json').write_text(json.dumps(self.meta('synthetic', source.path)))
        self.recording('synthetic', directory='samples/synthetic/learning')
        sources, errors = discover(self.root)
        self.assertEqual(errors, [])
        self.assertEqual([item.path for item in sources], [source.path])

    def test_ambiguous_duplicate_sessions_are_not_published(self):
        self.recording(directory='samples/a')
        self.recording(directory='samples/b')
        sources, errors = discover(self.root)
        self.assertEqual(sources, [])
        self.assertIn('ambiguous', errors[0])

    def test_cli_environment_output_override_and_isolated_failure(self):
        self.recording('good')
        bad = self.recording('bad')
        bad.path.write_text('garbage\n')
        with patch.dict(os.environ, {'DATA_DIR': str(self.root)}):
            code, stdout, stderr = self.invoke('--output-dir', str(self.root / 'custom'))
        self.assertEqual(code, 1)
        self.assertIn('archived=1 failed=1', stdout)
        self.assertIn('Archive failed:', stderr)
        self.assertTrue((self.root / 'custom' / 'good.parquet').exists())
        self.assertFalse(self.output.exists())

    def test_unsafe_id_cannot_escape_output_directory(self):
        source = self.recording()
        source.path.write_text('{"session_id":"../escape"}\n')
        sources, errors = discover(self.root)
        self.assertEqual(sources, [])
        self.assertIn('unsafe session id', errors[0])

    def test_missing_data_directory_and_bad_zip_report_failure(self):
        self.assertEqual(self.invoke('--data-dir', str(self.root / 'missing'))[0], 1)
        samples = self.root / 'samples'
        samples.mkdir()
        (samples / 'bad.zip').write_text('bad ZIP')
        code, stdout, stderr = self.invoke('--data-dir', str(self.root))
        self.assertEqual(code, 1)
        self.assertIn('archived=0 failed=1', stdout)
        self.assertIn('Archive failed:', stderr)


if __name__ == '__main__':
    unittest.main()
