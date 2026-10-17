import argparse
import asyncio
import sys

import uvicorn

import analytics
import brain
import replay
from store import Store, data_dir

PORTS = {"brain": 8765, "replay": 8766, "analytics": 8767}


def parse(argv):
    ap = argparse.ArgumentParser(description="Kumite mock servers: brain :8765, replay :8766, analytics :8767, from recordings")
    ap.add_argument("--recording", action="append", help="recording JSONL to serve (repeatable); default: data/samples/*.jsonl and DATA_DIR/recordings/*.jsonl")
    ap.add_argument("--rate", type=int, default=60, help="frames per second for the WebSocket streams")
    ap.add_argument("--no-loop", action="store_true", help="stop the WebSocket streams at the end of the session instead of looping")
    ap.add_argument("--skip", action="append", default=[], choices=sorted(PORTS), help="don't serve this API (repeatable), e.g. --skip analytics when the real service runs")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--no-synthetic", action="store_true", help="don't generate the synthetic session")
    return ap.parse_args(argv)


def ensure_synthetic():
    try:
        import synth
    except ImportError:
        return None
    try:
        return synth.ensure(data_dir())
    except Exception as e:
        print(f"synthetic session skipped: {type(e).__name__}: {e}", flush=True)
        return None


async def main(argv=None):
    a = parse(argv)
    if not a.no_synthetic and not a.recording:
        ensure_synthetic()
    store = Store(a.recording)
    apps = {
        "brain": lambda: brain.create(store, rate=a.rate, loop=not a.no_loop),
        "replay": lambda: replay.create(store),
        "analytics": lambda: analytics.create(store),
    }
    servers = []
    default = store.default()
    print(f"{len(store.sessions)} session(s) loaded; default stream: {default.id if default else 'none'}", flush=True)
    for s in store.newest():
        print(f"  {s.id}  ({s.meta.get('mode', '?')}, {len(s.records)} records)", flush=True)
    for name, port in PORTS.items():
        if name in a.skip:
            print(f"{name:<9} skipped", flush=True)
            continue
        config = uvicorn.Config(apps[name](), host=a.host, port=port, log_level="warning")
        servers.append(uvicorn.Server(config))
        print(f"{name:<9} http://localhost:{port}", flush=True)
    if not servers:
        print("nothing to serve", file=sys.stderr)
        return 1
    await asyncio.gather(*(s.serve() for s in servers))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        pass
