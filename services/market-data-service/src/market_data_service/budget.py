import math
import threading
import time
from collections import deque

from desk_runtime.db import session_scope
from desk_runtime.functions import utcnow
from desk_domain.models import ProviderRequestLedger


class RollingMinuteBudget:
    WINDOW_SECONDS = 60

    def __init__(self, capacity):
        self.capacity = capacity
        self._events = deque()
        self._used = 0
        self._lock = threading.Lock()

    def _expire(self, now):
        cutoff = now - self.WINDOW_SECONDS
        while self._events and self._events[0][0] <= cutoff:
            _, cost = self._events.popleft()
            self._used -= cost

    def try_take(self, cost=1):
        if cost < 1 or cost > self.capacity:
            return False
        with self._lock:
            now = time.monotonic()
            self._expire(now)
            if self._used + cost > self.capacity:
                return False
            self._events.append((now, cost))
            self._used += cost
            return True

    def seconds_until_available(self, cost=1):
        if cost < 1 or cost > self.capacity:
            return None
        with self._lock:
            now = time.monotonic()
            self._expire(now)
            needed = self._used + cost - self.capacity
            if needed <= 0:
                return 0
            released = 0
            for happened_at, event_cost in self._events:
                released += event_cost
                if released >= needed:
                    return max(
                        0,
                        math.ceil(happened_at + self.WINDOW_SECONDS - now),
                    )
        return None

    def state(self):
        with self._lock:
            self._expire(time.monotonic())
            return {
                "tokens_available": self.capacity - self._used,
                "capacity": self.capacity,
                "window_seconds": self.WINDOW_SECONDS,
            }


class DailyLedger:
    def __init__(self, daily_budget=None, provider_limit=None, provider=None, persisted=False):
        self._daily_budget = daily_budget
        self._provider_limit = provider_limit
        self._provider = provider
        self._persisted = persisted
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
        if self._persisted:
            now = utcnow()
            with session_scope() as session:
                row = (
                    session.query(ProviderRequestLedger)
                    .filter_by(provider=self._provider, usage_date=now.date())
                    .with_for_update()
                    .one_or_none()
                )
                if row is None:
                    row = ProviderRequestLedger(
                        provider=self._provider,
                        usage_date=now.date(),
                        requests=0,
                        credits=0,
                        updated_at=now,
                    )
                    session.add(row)
                row.requests += 1
                row.credits += credits
                row.updated_at = now
            return
        with self._lock:
            self._roll_day()
            self._requests += 1
            self._credits += credits

    def credits_today(self):
        if self._persisted:
            return self._persisted_state()[1]
        with self._lock:
            self._roll_day()
            return self._credits

    def state(self):
        if self._persisted:
            requests, credits = self._persisted_state()
            state = {"requests_today": requests, "persisted": True}
            if self._daily_budget is not None:
                state.update({
                    "credits_today": credits,
                    "daily_budget": self._daily_budget,
                    "provider_daily_limit": self._provider_limit,
                })
            return state
        with self._lock:
            self._roll_day()
            state = {"requests_today": self._requests}
            if self._daily_budget is not None:
                state["credits_today"] = self._credits
                state["daily_budget"] = self._daily_budget
                state["provider_daily_limit"] = self._provider_limit
            return state

    def _persisted_state(self):
        with session_scope() as session:
            row = session.get(
                ProviderRequestLedger,
                {"provider": self._provider, "usage_date": utcnow().date()},
            )
            return (row.requests, row.credits) if row is not None else (0, 0)
