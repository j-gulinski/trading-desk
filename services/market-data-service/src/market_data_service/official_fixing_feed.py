import time
from abc import ABC, abstractmethod
from datetime import datetime, time as time_of_day, timedelta, timezone
from zoneinfo import ZoneInfo

from desk_runtime.functions import utcnow
from desk_runtime.logging_config import get_logger
from market_data_service import quote_board
from market_data_service.config import (
    OFFICIAL_FIXING_FEED_CONFIRM_SECONDS,
    OFFICIAL_FIXING_FEED_LOOP_SLEEP_SECONDS,
    OFFICIAL_FIXING_FEED_PUBLICATION_GRACE_SECONDS,
    OFFICIAL_FIXING_FEED_WINDOW_RETRY_SECONDS,
    SERVICE_NAME,
)
from market_data_service.providers.base import ProviderDataError

log = get_logger(SERVICE_NAME)

BUSINESS_WEEKDAYS = range(5)


class PublicationCalendar:
    """The local business-day window in which an official fixing is published."""

    def __init__(self, tz_name, window_start, window_end):
        self.tz = ZoneInfo(tz_name)
        self.window_start = time_of_day(*window_start)
        self.window_end = time_of_day(*window_end)

    def source_today(self, now):
        return now.astimezone(self.tz).date()

    def in_window(self, now):
        local = now.astimezone(self.tz)
        return (
            local.weekday() in BUSINESS_WEEKDAYS
            and self.window_start <= local.time() <= self.window_end
        )

    def _next_publication_end(self, after_date):
        day = after_date + timedelta(days=1)
        while day.weekday() not in BUSINESS_WEEKDAYS:
            day += timedelta(days=1)
        return datetime.combine(day, self.window_end, tzinfo=self.tz)

    def stale_after_seconds(self, as_of_date):
        as_of = datetime.combine(as_of_date, time_of_day(0, 0), tzinfo=timezone.utc)
        deadline = self._next_publication_end(as_of_date).astimezone(timezone.utc)
        return round(
            (deadline - as_of).total_seconds()
            + OFFICIAL_FIXING_FEED_PUBLICATION_GRACE_SECONDS
        )

    def next_window_seconds(self, now):
        if self.in_window(now):
            return 0
        local = now.astimezone(self.tz)
        day = local.date()
        if local.weekday() not in BUSINESS_WEEKDAYS or local.time() > self.window_start:
            day = self._next_publication_end(day).date()
        opens = datetime.combine(day, self.window_start, tzinfo=self.tz)
        return round((opens - local).total_seconds())

    def describe_window(self):
        start = self.window_start.strftime("%H:%M")
        end = self.window_end.strftime("%H:%M")
        city = self.tz.key.split("/")[-1].replace("_", " ")
        return f"{start}–{end} {city} time, business days"


class OfficialFixingFeed(ABC):
    """Polls one official fixing table around its publication window."""

    def __init__(self, provider, runtime, client, calendar):
        self.provider = provider
        self.runtime = runtime
        self.client = client
        self.calendar = calendar
        self._last_fetch = None
        self._latest_as_of = None

    @abstractmethod
    def fetch(self, symbols):
        """Reference quotes published for symbols."""

    def request_cost(self, symbols):
        return 1

    def symbols(self):
        return quote_board.fixing_symbols(self.provider)

    def active_symbols(self):
        return sorted(self.symbols())

    def _classifier(self, as_of_date):
        return {
            "stale_after_seconds": self.calendar.stale_after_seconds(as_of_date),
            "closed_stale_after_seconds": None,
            "market_open": None,
        }

    def _store_round(self, quotes):
        ticks = {}
        for quote in quotes:
            as_of = quote.provider_timestamp.date()
            try:
                ticks[quote.symbol] = quote_board.store_and_publish(quote, self._classifier(as_of))
            except ProviderDataError as error:
                log.info("official_fixing_not_stored", provider=self.provider,
                         symbol=quote.symbol, detail=error.detail)
                continue
            if self._latest_as_of is None or as_of > self._latest_as_of:
                self._latest_as_of = as_of
        return ticks

    def _fetch_round(self):
        self._last_fetch = time.monotonic()
        symbols = self.active_symbols()
        cost = self.request_cost(symbols)
        refusal = self.runtime.acquire(cost, calls=cost)
        if refusal is not None:
            return {}, refusal
        quotes, error = self.runtime.guarded(
            lambda: self.fetch(symbols), "official_fixing_unavailable",
        )
        if error is not None:
            return {}, error
        ticks = self._store_round(quotes)
        self.runtime.record_success()
        return ticks, None

    def _awaiting_publication(self, now):
        today = self.calendar.source_today(now)
        return self._latest_as_of is None or self._latest_as_of < today

    def _retry_interval(self, now):
        if self.calendar.in_window(now) and self._awaiting_publication(now):
            return OFFICIAL_FIXING_FEED_WINDOW_RETRY_SECONDS
        return OFFICIAL_FIXING_FEED_CONFIRM_SECONDS

    def poll_loop(self):
        while True:
            try:
                self._poll_tick()
            except Exception:
                log.exception("official_fixing_feed_tick_failed", provider=self.provider)
            time.sleep(OFFICIAL_FIXING_FEED_LOOP_SLEEP_SECONDS)

    def _poll_tick(self):
        # paused by a cooldown: poll nothing
        if self.runtime.cooldown_seconds_left() > 0:
            return
        # served fixings: defaults + settlement currencies of trades
        quote_board.reload_if_stale()
        # window polling until a new as-of appears, else bounded confirmation polls
        if self._last_fetch is None or (
            time.monotonic() - self._last_fetch >= self._retry_interval(utcnow())
        ):
            self._fetch_round()

    def refresh_symbol(self, symbol):
        """Fetches the fixing table now; returns (tick, error, http_status)."""
        if symbol not in self.symbols():
            quote_board.reload()
        if symbol not in self.symbols():
            return None, f"{symbol} is not in the {self.provider} reference set", 404
        unavailable = self.runtime.unavailable()
        if unavailable is not None:
            return None, unavailable, 503
        ticks, error = self._fetch_round()
        tick = ticks.get(symbol)
        if tick is None:
            return None, error or f"{self.provider} has not published {symbol}", 502
        return tick, None, 200

    def refresh_all(self):
        """Fetches the fixing table now; returns (refreshed, skipped)."""
        quote_board.reload_if_stale()
        symbols = self.active_symbols()
        if self.runtime.cooldown_seconds_left() > 0:
            reason = f"{self.provider} is {self.runtime.status()}"
            return [], [{"provider": self.provider, "symbol": symbol, "reason": reason}
                        for symbol in symbols]
        ticks, error = self._fetch_round()
        refreshed = [{"provider": self.provider, "symbol": symbol} for symbol in sorted(ticks)]
        skipped = [{"provider": self.provider, "symbol": symbol,
                    "reason": error or "no published fixing"}
                   for symbol in symbols if symbol not in ticks]
        return refreshed, skipped

    def strategy(self):
        now = utcnow()
        window = self.calendar.describe_window()
        next_window = self.calendar.next_window_seconds(now)
        if self.calendar.in_window(now):
            state = (
                "window open — polling for today's fixing every "
                f"{OFFICIAL_FIXING_FEED_WINDOW_RETRY_SECONDS // 60} min"
                if self._awaiting_publication(now)
                else "today's fixing received — hourly confirmation"
            )
        else:
            hours, minutes = divmod(max(0, next_window) // 60, 60)
            state = f"next window in {hours}h {minutes:02d}m — hourly confirmation"
        return {
            "mode": "PUBLICATION_CALENDAR",
            "window": window,
            "next_window_seconds": next_window,
            "last_as_of": str(self._latest_as_of) if self._latest_as_of else None,
            "window_retry_seconds": OFFICIAL_FIXING_FEED_WINDOW_RETRY_SECONDS,
            "confirm_seconds": OFFICIAL_FIXING_FEED_CONFIRM_SECONDS,
            "description": f"fixings {window} · {state}",
        }

    def runtime_snapshot(self):
        return {
            **self.runtime.snapshot(self.active_symbols()),
            "strategy": self.strategy(),
        }
