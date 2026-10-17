import argparse
import json
import socket
import sys
import threading
import time

from game.pad import KillSwitch, Pad, load_config

RECV_TIMEOUT_S = 0.02
WATCHDOG_S = 2.0
KILL_HOLDOFF_S = 1.0
MENU_HOLD_S = 0.1
MENU_HELP = "keys: u d l r a b x y start back lb rb (combine with +, e.g. d+a), several per line, Enter to send, q to quit"


def press_menu(pad, lock, line, log=print):
    keys = line.split()
    for key in keys:
        try:
            with lock:
                pad.menu(key.split("+"))
        except KeyError:
            log(f"unknown key {key!r}")
            continue
        time.sleep(MENU_HOLD_S)
        with lock:
            pad.release_all()
        time.sleep(MENU_HOLD_S)
    return keys


def console(pad, lock, stop):
    print(MENU_HELP, flush=True)
    for line in sys.stdin:
        if line.strip() == "q":
            break
        keys = press_menu(pad, lock, line)
        if keys:
            print("sent " + " ".join(keys), flush=True)
    stop.set()


class Server:
    def __init__(self, pad, sock):
        self.pad = pad
        self.sock = sock
        self.lock = threading.Lock()
        self.last_message = time.monotonic()
        self.holdoff_until = 0.0
        self.client = None
        self.messages = 0

    def handle(self, data, addr):
        try:
            msg = json.loads(data)
        except ValueError:
            return
        op = msg.get("op")
        self.last_message = time.monotonic()
        self.messages += 1
        if addr != self.client:
            self.client = addr
            print(f"client {addr[0]}:{addr[1]} connected", flush=True)
        if op == "hello":
            self.sock.sendto(json.dumps({"ok": True}).encode(), addr)
        elif op == "release":
            with self.lock:
                self.pad.release_all()
        elif op == "set" and time.monotonic() >= self.holdoff_until:
            names = [n for n in msg.get("names", []) if n in self.pad.codes]
            with self.lock:
                self.pad.set_names(names)

    def tick(self):
        try:
            self.pad.check_kill()
        except KillSwitch as e:
            self.holdoff_until = time.monotonic() + KILL_HOLDOFF_S
            print(f"{e}: released everything; pad stays plugged in", flush=True)
        if self.pad.held and time.monotonic() - self.last_message > WATCHDOG_S:
            with self.lock:
                self.pad.release_all()
            print(f"watchdog: no client message for {WATCHDOG_S:.0f} s, released everything", flush=True)

    def serve(self, stop):
        self.sock.settimeout(RECV_TIMEOUT_S)
        while not stop.is_set():
            try:
                data, addr = self.sock.recvfrom(4096)
                self.handle(data, addr)
            except socket.timeout:
                pass
            except ConnectionResetError:
                pass
            self.tick()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Own the virtual 2P pad for the whole session so it never unplugs between runs")
    parser.add_argument("--no-console", action="store_true", help="do not read menu keys from stdin")
    args = parser.parse_args(argv)

    config = load_config()
    host, port = config["server"]["host"], config["server"]["port"]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((host, port))
    except OSError as e:
        print(f"cannot bind {host}:{port} ({e}); is another padserver running?", flush=True)
        return 1
    pad = Pad(config)
    server = Server(pad, sock)
    stop = threading.Event()
    print(f"padserver: virtual Xbox 360 pad plugged in, listening on {host}:{port}. "
          f"If Tekken has not seen it yet, type 'start' to register it as 2P and 'start' again to close the menu. "
          f"Kill key {config['kill_key']} releases everything. Ctrl+C or q to unplug.", flush=True)
    if not args.no_console:
        threading.Thread(target=console, args=(pad, server.lock, stop), daemon=True).start()
    try:
        server.serve(stop)
    except KeyboardInterrupt:
        pass
    finally:
        pad.release_all()
        sock.close()
        print(f"padserver stopped after {server.messages} messages; pad unplugged", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
