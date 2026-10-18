import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

import httpx


def sessions_in(data_dir, last, names):
    folder = Path(data_dir) / "recordings"
    if names:
        return [folder / f"{name}.jsonl" for name in names]
    paths = sorted(path for path in folder.glob("*.jsonl") if path.is_file())
    return paths[-last:] if last else paths


def summaries_in(path):
    rows = []
    with path.open("rb") as source:
        for line in source:
            if b'"round_summary"' not in line:
                continue
            try:
                data = json.loads(line.decode("utf-8", errors="replace"))
            except ValueError:
                continue
            if data.get("t") == "round_summary":
                rows.append(data)
    rows.sort(key=lambda row: row.get("round", 0))
    return rows


async def replay(app, paths, show_candidates):
    topics = Counter()
    chosen = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://replay") as client:
        for path in paths:
            rows = summaries_in(path)
            print(f"== {path.stem}: {len(rows)} round summaries")
            for summary in rows:
                response = await client.post("/coach/round", json=summary)
                if response.status_code != 200:
                    print(f"  r{summary.get('round')}: HTTP {response.status_code} {response.text[:200]}")
                    continue
                tip = response.json()
                last = app.state.coach.last or {}
                topic = last.get("topic") or "summary_only"
                topics[topic] += 1
                chosen.append((path.stem, summary.get("round"), topic))
                print(f"  r{summary.get('round')} [{tip['severity']}] {topic} ({last.get('source')}, {len(tip['text'].split())} words): {tip['text']}")
                if show_candidates:
                    for candidate in last.get("candidates", []):
                        print(f"      {candidate['topic']:14} score={candidate['score']:>7} damage={candidate['damage']:>3} | {candidate['text']}")
    return topics, chosen


def main(argv=None):
    parser = argparse.ArgumentParser(description="Replay recorded round summaries through POST /coach/round offline")
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "data"))
    parser.add_argument("--last", type=int, default=3, help="replay the last N sessions by name")
    parser.add_argument("--session", action="append", default=[], help="replay this session id (repeatable)")
    parser.add_argument("--min-topics", type=int, default=4)
    parser.add_argument("--candidates", action="store_true", help="print every ranked candidate per round")
    parser.add_argument("--mode", choices=("local", "auto"), default="local", help="auto uses OPENAI_API_KEY when present")
    args = parser.parse_args(argv)
    os.environ["DATA_DIR"] = str(Path(args.data_dir).resolve())
    os.environ["KUMITE_COACH_MODE"] = args.mode
    os.environ.setdefault("SENTRY_DSN", "")
    from replay.main import create_app

    app = create_app()
    paths = [path for path in sessions_in(args.data_dir, args.last, args.session) if path.is_file()]
    if not paths:
        print("no recordings found", file=sys.stderr)
        return 2
    topics, chosen = asyncio.run(replay(app, paths, args.candidates))
    print(f"\n{len(topics)} distinct topics across {len(chosen)} rounds: " + ", ".join(f"{topic} x{count}" for topic, count in topics.most_common()))
    if len(topics) < args.min_topics:
        print(f"FAIL: fewer than {args.min_topics} topics", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
