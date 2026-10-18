import argparse
import asyncio
import json
import os
import sys
import threading
import time

REPLAY_URL = "http://127.0.0.1:8766"
TIMEOUT = 8.0
CLOSE_WAIT = 9.0
STATE_EVERY = 2
SEVERITIES = ("info", "warn", "praise")
FALLBACK = "Coach offline: after a blocked string, keep blocking and punish only what is unsafe."
WATCH_URL = "ws://127.0.0.1:8765/ws/coach"


def replay_url():
    return os.environ.get("KUMITE_REPLAY_URL", REPLAY_URL).rstrip("/")


def tip_from(reply):
    if not isinstance(reply, dict):
        return None
    text = reply.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    severity = reply.get("severity")
    return text.strip(), severity if severity in SEVERITIES else "info"


class Outlet:
    def __init__(self, publish, url=None, timeout=TIMEOUT, log=print, transport=None):
        self.publish = publish
        self.url = url
        self.timeout = timeout
        self.log = log
        self.transport = transport
        self.last = None
        self.threads = []

    def _send(self, record):
        try:
            self.publish(record)
        except Exception:
            pass

    def state(self, gs):
        try:
            key = (gs["round"], gs["frame"])
            if self.last is None or key[0] != self.last[0] or key[1] < self.last[1] or key[1] - self.last[1] >= STATE_EVERY:
                self.last = key
                self._send(gs)
        except Exception:
            pass

    def records(self, recs):
        for rec in recs:
            self._send(rec)
            if isinstance(rec, dict) and rec.get("t") == "round_summary":
                self._coach(rec)

    def _coach(self, summary):
        try:
            thread = threading.Thread(target=self._ask, args=(summary,), name=f"coach-r{summary.get('round')}", daemon=True)
            self.threads = [t for t in self.threads if t.is_alive()] + [thread]
            thread.start()
        except Exception as e:
            self.log(f"coach r{summary.get('round')}: could not start the request ({e!r})")

    def _ask(self, summary):
        import httpx

        source = "replay"
        reason = None
        tip = None
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.post(f"{self.url or replay_url()}/coach/round", json=summary)
            if response.status_code != 200:
                reason = f"HTTP {response.status_code}"
            else:
                tip = tip_from(response.json())
                if tip is None:
                    reason = "reply had no text"
        except Exception as e:
            reason = type(e).__name__
        if tip is None:
            source = f"fallback, {reason}"
            tip = (FALLBACK, "info")
        text, severity = tip
        self._send({"t": "coach", "session_id": summary.get("session_id"), "round": summary.get("round"), "text": text, "severity": severity})
        self.log(f"coach r{summary.get('round')} ({source}): {text}")

    def close(self, wait=CLOSE_WAIT):
        deadline = time.monotonic() + wait
        for thread in self.threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        self.threads = [t for t in self.threads if t.is_alive()]
        return not self.threads


def show(rec):
    if rec.get("t") == "coach":
        return f"coach r{rec.get('round')} [{rec.get('severity')}]: {rec.get('text')}"
    if rec.get("t") == "round_summary":
        habits = "; ".join(f"{h['situation']} {h['action']} p={h['p']:.2f}" for h in rec.get("top_habits", []))
        return (f"round_summary r{rec.get('round')} winner {rec.get('winner')} human took {rec.get('human_damage_taken')} "
                f"bot took {rec.get('bot_damage_taken')}; {habits or 'no habits yet'}")
    return json.dumps(rec)


async def watch(url, retry=1.0):
    import websockets

    waiting = False
    while True:
        try:
            async with websockets.connect(url) as ws:
                print(f"connected to {url}", flush=True)
                waiting = False
                async for text in ws:
                    print(show(json.loads(text)), flush=True)
            print(f"{url} closed; waiting for the brain API", flush=True)
            waiting = True
        except (OSError, websockets.ConnectionClosed, websockets.InvalidHandshake) as e:
            if not waiting:
                print(f"waiting for the brain API at {url} ({type(e).__name__}); start game.bot", flush=True)
                waiting = True
        await asyncio.sleep(retry)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kumite coach stream: print coach tips and round summaries from the brain API")
    sub = parser.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("watch")
    w.add_argument("--url", default=WATCH_URL)
    args = parser.parse_args(argv)
    try:
        asyncio.run(watch(args.url))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
