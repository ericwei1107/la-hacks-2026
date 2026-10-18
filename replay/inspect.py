import argparse
import sys

from replay.config import Settings
from replay.inspection import build_inspection, write_inspection
from replay.reader import read_recording


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect a local recording without model calls")
    parser.add_argument("recording", help="Extracted JSONL path")
    parser.add_argument("--output-dir", help="Default: DATA_DIR/inspections")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        recording = read_recording(args.recording)
        report = build_inspection(recording)
        output_dir = args.output_dir or Settings.load().data_dir / "inspections"
        paths = write_inspection(report, output_dir, overwrite=args.overwrite)
    except (OSError, ValueError) as error:
        print(f"Inspection failed: {error}", file=sys.stderr)
        return 1
    print(f"Inspected {sum(recording.counts.values())} records; {len(report['moments'])} observed moments")
    for path in paths:
        print(path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
