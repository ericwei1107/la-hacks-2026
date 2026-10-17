import time

POLL_HZ = 1000
SPIN_MARGIN = 0.0006


class Pacer:
    def __init__(self, hz=POLL_HZ):
        self.period = 1.0 / hz
        self.start = time.perf_counter()
        self.deadline = self.start
        self.polls = 0

    def wait(self):
        self.polls += 1
        self.deadline += self.period
        delay = self.deadline - time.perf_counter()
        if delay <= -self.period:
            self.deadline = time.perf_counter()
        while delay > 0:
            time.sleep(delay - SPIN_MARGIN if delay > SPIN_MARGIN else 0)
            delay = self.deadline - time.perf_counter()

    def rate(self):
        elapsed = time.perf_counter() - self.start
        return elapsed, (self.polls / elapsed if elapsed > 0 else 0.0)
