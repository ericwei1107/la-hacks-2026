import argparse
from contextlib import contextmanager
import asyncio
import signal
import socket
import sys

import uvicorn

import analytics_mock
import brain
import replay_mock
from store import Store

PORTS = {"brain": 8765, "replay": 8766, "analytics": 8767}


@contextmanager
def shutdown_signals(loop, stop):
    registered, fallback = [], {}
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
                registered.append(sig)
            except NotImplementedError:
                fallback[sig] = signal.getsignal(sig)
                signal.signal(sig, lambda signum, frame: loop.call_soon_threadsafe(stop.set))
        yield
    finally:
        for sig in registered:
            loop.remove_signal_handler(sig)
        for sig, previous in fallback.items():
            signal.signal(sig, previous)


class Server(uvicorn.Server):
    @contextmanager
    def capture_signals(self):
        yield


def parse(argv):
    ap = argparse.ArgumentParser(description="Kumite recording-backed mock APIs")
    ap.add_argument("--recording", action="append", help="select a recording (repeatable; first is streamed)")
    ap.add_argument("--rate", type=int, default=60)
    ap.add_argument("--no-loop", action="store_true")
    ap.add_argument("--services", default="brain,replay,analytics")
    ap.add_argument("--skip", action="append", default=[], choices=sorted(PORTS))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--experimental-insights", action="store_true", help="serve the unapproved GET /insights/{id} from DATA_DIR on mock analytics")
    args = ap.parse_args(argv)
    args.services = args.services.split(",")
    if args.rate <= 0 or not args.services or any(s not in PORTS for s in args.services):
        ap.error("use a positive --rate and comma-separated --services brain,replay,analytics")
    args.services = list(dict.fromkeys(s for s in args.services if s not in args.skip))
    if not args.services:
        ap.error("select at least one service")
    return args


async def main(argv=None):
    a = parse(argv)
    store = Store(a.recording)
    if not store.sessions:
        raise ValueError("No recordings loaded; pass --recording PATH with companion session metadata")
    apps = {
        "brain": lambda: brain.create(store, rate=a.rate, loop=not a.no_loop),
        "replay": lambda: replay_mock.create(store),
        "analytics": lambda: analytics_mock.create(store, insights=a.experimental_insights),
    }
    sockets, servers, tasks = [], [], []
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    handlers = shutdown_signals(loop, stop)
    with handlers:
        return await serve_apps(a, store, apps, sockets, servers, tasks, loop, stop)


async def serve_apps(a, store, apps, sockets, servers, tasks, loop, stop):
    try:
        for name in a.services:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sockets.append(sock)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((a.host, PORTS[name]))
                sock.listen(128)
                sock.setblocking(False)
            except OSError as exc:
                raise OSError(f"Cannot start {name} on {a.host}:{PORTS[name]}: {exc}") from exc
        print(f"{len(store.sessions)} session(s) loaded; default stream: {store.default().id}", flush=True)
        for name, sock in zip(a.services, sockets):
            server = Server(uvicorn.Config(apps[name](), host=a.host, port=PORTS[name], log_level="warning"))
            server.install_signal_handlers = lambda: None
            servers.append(server)
            tasks.append(asyncio.create_task(server.serve(sockets=[sock])))
            print(f"{name:<9} http://{a.host}:{PORTS[name]}", flush=True)
        stopped = asyncio.create_task(stop.wait())
        done, _ = await asyncio.wait([*tasks, stopped], return_when=asyncio.FIRST_COMPLETED)
        stopped.cancel()
        await asyncio.gather(stopped, return_exceptions=True)
        for task in done:
            if task is not stopped:
                task.result()
        return 0 if stop.is_set() else 1
    finally:
        for server in servers:
            server.should_exit = True
        if tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5)
            except asyncio.TimeoutError:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        for sock in sockets:
            sock.close()


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass
