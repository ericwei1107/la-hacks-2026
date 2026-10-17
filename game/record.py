import argparse
import sys

from game import state as st
from game.hotloop import run_session
from game.reader import DEFAULT_OFFSETS, Reader
from game.readout import run_gate


def add_session_args(parser):
    parser.add_argument("--player", required=True)
    parser.add_argument("--bot", required=True, choices=st.CHARACTERS)
    parser.add_argument("--difficulty", type=int, default=1, choices=range(1, 6))
    parser.add_argument("--mode", default="practice", choices=("practice", "versus"))
    parser.add_argument("--stage")
    parser.add_argument("--offsets", default=str(DEFAULT_OFFSETS))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kumite recorder: GameState and events per contracts/recording.md")
    add_session_args(parser)
    args = parser.parse_args(argv)

    reader = Reader(args.offsets)
    try:
        if not run_gate(reader, args.offsets):
            return 1
        run_session(reader, args)
        return 0
    finally:
        reader.close()


if __name__ == "__main__":
    sys.exit(main())
