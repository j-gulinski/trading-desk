import threading
import time

from shared.functions import utcnow


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

    def try_take(self, cost=1):
        with self._lock:
            self._refill()
            if self._tokens < cost:
                return False
            self._tokens -= cost
            return True

    def state(self):
        with self._lock:
            self._refill()
            return {"tokens_available": int(self._tokens), "capacity": self.capacity}


class DailyLedger:
    def __init__(self, daily_budget=None):
        self._daily_budget = daily_budget
        self._day = utcnow().date()
        self._requests = 0
        self._credits = 0
        self._lock = threading.Lock()

    def _roll_day(self):
        today = utcnow().date()
        if today != self._day:
            self._day = today
            self._requests = 0
            self._credits = 0

    def record(self, credits=1):
        with self._lock:
            self._roll_day()
            self._requests += 1
            self._credits += credits

    def credits_today(self):
        with self._lock:
            self._roll_day()
            return self._credits

    def state(self):
        with self._lock:
            self._roll_day()
            state = {"requests_today": self._requests}
            if self._daily_budget is not None:
                state["credits_today"] = self._credits
                state["daily_budget"] = self._daily_budget
            return state
