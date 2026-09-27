import math
import threading
import time
from collections import deque

from desk_domain.models import ProviderRequestLedger
from desk_runtime.db import session_scope
from desk_runtime.functions import utcnow
from market_data_service.config import PROVIDER_ACTIVE_WINDOW_HOURS, PROVIDER_BUDGET_USAGE_PERCENT

WINDOW_SECONDS = 60


class RequestBudget:
    """Request spacing, per-minute and per-day limits of one provider; counts calls per day."""

    def __init__(self, provider, per_minute=None, per_day=None, min_interval_seconds=None,
                 provider_minute_limit=None, provider_daily_limit=None):
        self.provider = provider
        self.per_minute = per_minute
        self.per_day = per_day
        self.min_interval_seconds = min_interval_seconds
        self.provider_minute_limit = provider_minute_limit
        self.provider_daily_limit = provider_daily_limit
        self._recent = deque()
        self._last_request_at = None
        self._lock = threading.Lock()

    def acquire(self, cost=1, calls=1):
        """Takes cost from every limit and counts the calls; returns a refusal reason or None."""
        with self._lock:
            now = time.monotonic()
            spacing = self._spacing_wait(now)
            if spacing > 0:
                return f"{self.provider} request spacing is active: retry in {spacing}s"
            if self._minute_wait(now, cost) > 0:
                return f"{self.provider} request budget is exhausted: retry shortly"
            if not self._count_today(cost, calls):
                return f"{self.provider} daily budget is spent for now: retry later"
            self._recent.append((now, cost))
            self._last_request_at = now
            return None

    def wait_seconds(self, cost=1):
        with self._lock:
            now = time.monotonic()
            return max(self._spacing_wait(now), self._minute_wait(now, cost))

    def credits_left_today(self):
        return self.per_day - self._today()[1]

    def state(self):
        requests, credits = self._today()
        state = {}
        if self.per_minute is not None:
            with self._lock:
                used = self._minute_used(time.monotonic())
            state.update(
                tokens_available=self.per_minute - used,
                capacity=self.per_minute,
                window_seconds=WINDOW_SECONDS,
                budget_per_minute=self.per_minute,
            )
        state["requests_today"] = requests
        if self.per_day is not None:
            state.update(
                persisted=True,
                credits_today=credits,
                daily_budget=self.per_day,
                provider_daily_limit=self.provider_daily_limit,
            )
        if self.provider_minute_limit is not None:
            state.update(
                provider_minute_limit=self.provider_minute_limit,
                usage_percent=PROVIDER_BUDGET_USAGE_PERCENT,
            )
        if self.per_minute is not None and self.per_day is not None:
            state["active_window_hours"] = PROVIDER_ACTIVE_WINDOW_HOURS
        if self.min_interval_seconds is not None:
            state["min_request_interval_seconds"] = self.min_interval_seconds
            state["next_request_seconds"] = self.wait_seconds()
        return state

    def _spacing_wait(self, now):
        if self.min_interval_seconds is None or self._last_request_at is None:
            return 0
        return max(0, math.ceil(self._last_request_at + self.min_interval_seconds - now))

    def _minute_used(self, now):
        while self._recent and self._recent[0][0] <= now - WINDOW_SECONDS:
            self._recent.popleft()
        return sum(cost for _, cost in self._recent)

    def _minute_wait(self, now, cost):
        if self.per_minute is None:
            return 0
        excess = self._minute_used(now) + cost - self.per_minute
        if excess <= 0:
            return 0
        for taken_at, taken in self._recent:
            excess -= taken
            if excess <= 0:
                return math.ceil(taken_at + WINDOW_SECONDS - now)
        return WINDOW_SECONDS

    def _count_today(self, cost, calls):
        now = utcnow()
        with session_scope() as session:
            row = (
                session.query(ProviderRequestLedger)
                .filter_by(provider=self.provider, usage_date=now.date())
                .with_for_update()
                .one_or_none()
            )
            used = row.credits if row is not None else 0
            if self.per_day is not None and used + cost > self.per_day:
                return False
            if row is None:
                row = ProviderRequestLedger(
                    provider=self.provider, usage_date=now.date(),
                    requests=0, credits=0, updated_at=now,
                )
                session.add(row)
            row.requests += calls
            row.credits += cost
            row.updated_at = now
        return True

    def _today(self):
        with session_scope() as session:
            row = session.get(
                ProviderRequestLedger,
                {"provider": self.provider, "usage_date": utcnow().date()},
            )
            return (row.requests, row.credits) if row is not None else (0, 0)
