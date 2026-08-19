import threading
import time
from datetime import date


class TokenBucket:
    def __init__(self, capacity, refill_per_second):
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self._tokens = float(capacity)
        self._refilled_at = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self):
        now = time.monotonic()
        self._tokens = min(
            self.capacity, self._tokens + (now - self._refilled_at) * self.refill_per_second
        )
        self._refilled_at = now

    def try_take(self):
        with self._lock:
            self._refill()
            if self._tokens < 1:
                return False
            self._tokens -= 1
            return True

    def state(self):
        with self._lock:
            self._refill()
            return {"tokens_available": int(self._tokens), "capacity": self.capacity}


class DailyLedger:
    def __init__(self):
        self._day = date.today()
        self._requests = 0
        self._lock = threading.Lock()

    def record(self):
        with self._lock:
            today = date.today()
            if today != self._day:
                self._day = today
                self._requests = 0
            self._requests += 1

    def state(self):
        with self._lock:
            if date.today() != self._day:
                return {"requests_today": 0}
            return {"requests_today": self._requests}
