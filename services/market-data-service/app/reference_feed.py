import time

from shared.functions import utcnow
from shared.logging_config import get_logger
from app import persistence
from app.clients.base import (
    ProviderDataError,
    ProviderError,
    ProviderRateLimited,
)
from app.config import (
    RATE_LIMIT_DEFAULT_COOLDOWN_SECONDS,
    REFERENCE_CONFIRM_SECONDS,
    REFERENCE_LOOP_SLEEP_SECONDS,
    REFERENCE_SET_REFRESH_SECONDS,
    REFERENCE_WINDOW_RETRY_SECONDS,
    SERVICE_NAME,
    TRANSIENT_ERROR_BACKOFF_SECONDS,
)
from app.publisher import publish_quote
from app.quote_audit import audit_first_quote

log = get_logger(SERVICE_NAME)


class ReferenceFeed:
    def __init__(self, provider, runtime, calendar, universe_fn, fetch_fn):
        self.provider = provider
        self.runtime = runtime
        self.calendar = calendar
        self.universe_fn = universe_fn
        self.fetch_fn = fetch_fn
        self._universe = frozenset()
        self._universe_loaded_at = 0.0
        self._last_fetch = 0.0
        self._latest_as_of = None

    def reload_universe(self):
        self._universe = self.universe_fn()
        self._universe_loaded_at = time.monotonic()

    def universe(self):
        if not self._universe:
            self.reload_universe()
        return self._universe

    def _classifier(self, as_of_date):
        return {
            "stale_after_seconds": self.calendar.stale_after_seconds(as_of_date),
            "closed_stale_after_seconds": None,
            "market_open": None,
        }

    def _wire_quote(self, quote, classifier):
        return {
            "provider": quote.provider,
            "symbol": quote.symbol,
            "asset_class": quote.asset_class,
            "currency": quote.currency,
            "bid": quote.bid,
            "ask": quote.ask,
            "last": quote.last,
            "mid": quote.mid,
            "price_basis": quote.price_basis,
            "quote_grade": quote.quote_grade,
            "previous_close": quote.previous_close,
            "provider_timestamp": quote.provider_timestamp,
            "received_at": quote.received_at,
            "event_time": quote.received_at,
            **classifier,
            "watched": False,
            "held": False,
            "benchmark": False,
            "reference": True,
        }

    def _store_round(self, quotes):
        ticks = {}
        for quote in quotes:
            classifier = self._classifier(quote.provider_timestamp.date())
            _, created = persistence.store_quote(quote, classifier)
            if created:
                audit_first_quote(self.provider, quote)
            tick = self._wire_quote(quote, classifier)
            publish_quote(tick)
            ticks[quote.symbol] = tick
            as_of = quote.provider_timestamp.date()
            if self._latest_as_of is None or as_of > self._latest_as_of:
                self._latest_as_of = as_of
        return ticks

    def _fetch_round(self):
        self._last_fetch = time.monotonic()
        try:
            quotes = self.fetch_fn(sorted(self.universe()))
        except ProviderRateLimited as error:
            cooldown = error.retry_after_seconds or RATE_LIMIT_DEFAULT_COOLDOWN_SECONDS
            self.runtime.enter_cooldown(
                "RATE_LIMITED", "rate limited", error.detail, cooldown,
                "PROVIDER_RATE_LIMITED", "WARNING",
            )
            return {}, f"{self.provider} is rate limited"
        except ProviderDataError as error:
            log.info("reference_fixing_unavailable", provider=self.provider,
                     detail=error.detail)
            return {}, error.detail
        except ProviderError as error:
            self.runtime.transient_error(error.detail, TRANSIENT_ERROR_BACKOFF_SECONDS)
            return {}, error.detail
        ticks = self._store_round(quotes)
        self.runtime.record_success()
        return ticks, None

    def _awaiting_publication(self, now):
        today = self.calendar.source_today(now)
        return self._latest_as_of is None or self._latest_as_of < today

    def _retry_interval(self, now):
        if self.calendar.in_window(now) and self._awaiting_publication(now):
            return REFERENCE_WINDOW_RETRY_SECONDS
        return REFERENCE_CONFIRM_SECONDS

    def poll_loop(self):
        while True:
            try:
                self._poll_tick()
            except Exception:
                log.exception("reference_feed_tick_failed", provider=self.provider)
            time.sleep(REFERENCE_LOOP_SLEEP_SECONDS)

    def _poll_tick(self):
        # paused by a cooldown: wait, poll nothing
        if self.runtime.cooldown_seconds_left() > 0:
            return
        # re-read defaults + settlement currencies of open trades
        if time.monotonic() - self._universe_loaded_at >= REFERENCE_SET_REFRESH_SECONDS:
            self.reload_universe()
        # window polling until a new as-of appears, else bounded confirmation polls
        if time.monotonic() - self._last_fetch >= self._retry_interval(utcnow()):
            self._fetch_round()

    def refresh_symbol(self, symbol):
        self.reload_universe()
        if symbol not in self._universe:
            return None, f"{symbol} is not in the {self.provider} reference set", 404
        cooldown_left = self.runtime.cooldown_seconds_left()
        if cooldown_left > 0:
            return None, (
                f"{self.provider} is {self.runtime.status()}: "
                f"retry in {round(cooldown_left)}s"
            ), 503
        ticks, error = self._fetch_round()
        tick = ticks.get(symbol)
        if tick is None:
            return None, error or f"{self.provider} has not published {symbol}", 502
        return tick, None, 200

    def refresh_table(self):
        self.reload_universe()
        if self.runtime.cooldown_seconds_left() > 0:
            reason = f"{self.provider} is {self.runtime.status()}"
            return [], [{"provider": self.provider, "symbol": symbol, "reason": reason}
                        for symbol in sorted(self._universe)]
        ticks, error = self._fetch_round()
        refreshed = [{"provider": self.provider, "symbol": symbol}
                     for symbol in sorted(ticks)]
        skipped = [{"provider": self.provider, "symbol": symbol,
                    "reason": error or "no published fixing"}
                   for symbol in sorted(self._universe - set(ticks))]
        return refreshed, skipped

    def poll_strategy(self):
        now = utcnow()
        window = self.calendar.describe_window()
        next_window = self.calendar.next_window_seconds(now)
        if self.calendar.in_window(now):
            state = (
                "window open — polling for today's fixing every "
                f"{REFERENCE_WINDOW_RETRY_SECONDS // 60} min"
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
            "window_retry_seconds": REFERENCE_WINDOW_RETRY_SECONDS,
            "confirm_seconds": REFERENCE_CONFIRM_SECONDS,
            "description": f"fixings {window} · {state}",
        }

    def active_symbols(self):
        return sorted(self.universe())

    def runtime_snapshot(self):
        return {
            **self.runtime.snapshot(self.active_symbols()),
            "strategy": self.poll_strategy(),
        }
