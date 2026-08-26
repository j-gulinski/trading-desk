import time

from shared.functions import utcnow
from shared.logging_config import get_logger
from app import quote_lifecycle, quote_store
from app.quote_cleanup import cleanup_reference_drops
from app.config import (
    OFFICIAL_FIXING_FEED_CONFIRM_SECONDS,
    OFFICIAL_FIXING_FEED_LOOP_SLEEP_SECONDS,
    OFFICIAL_FIXING_FEED_UNIVERSE_REFRESH_SECONDS,
    OFFICIAL_FIXING_FEED_WINDOW_RETRY_SECONDS,
    SERVICE_NAME,
)
from app.publisher import publish_quote
from app.quote_audit import audit_quote_write
from shared.quotes import wire_tick

log = get_logger(SERVICE_NAME)


class OfficialFixingFeed:
    def __init__(self, provider, runtime, calendar, universe_fn, fetch_fn):
        self.provider = provider
        self.runtime = runtime
        self.calendar = calendar
        self.universe_fn = universe_fn
        self.fetch_fn = fetch_fn
        self._universe = frozenset()
        self._universe_loaded_at = 0.0
        self._last_fetch = None
        self._latest_as_of = None

    def reload_universe(self):
        previous = self._universe
        self._universe = self.universe_fn()
        self._universe_loaded_at = time.monotonic()
        cleanup_reference_drops(
            self.provider,
            previous - self._universe,
            self.universe_fn,
        )

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

    def _store_round(self, quotes):
        ticks = {}
        for quote in quotes:
            with quote_lifecycle.locked_keys(quote.symbol, (self.provider,)):
                if quote.symbol not in self.universe_fn():
                    log.info(
                        "reference_observation_dropped_after_universe_change",
                        provider=self.provider,
                        symbol=quote.symbol,
                    )
                    continue
                classifier = self._classifier(quote.provider_timestamp.date())
                changed, created, accepted = quote_store.store_quote(quote, classifier)
                if not accepted:
                    log.info(
                        "older_reference_observation_ignored",
                        provider=self.provider,
                        symbol=quote.symbol,
                    )
                    continue
                if changed:
                    audit_quote_write(self.provider, quote, created)
                tick = wire_tick(quote, classifier, reference=True)
                publish_quote(tick)
            ticks[quote.symbol] = tick
            as_of = quote.provider_timestamp.date()
            if self._latest_as_of is None or as_of > self._latest_as_of:
                self._latest_as_of = as_of
        return ticks

    def _fetch_round(self):
        self._last_fetch = time.monotonic()
        quotes, error = self.runtime.guarded(
            lambda: self.fetch_fn(sorted(self.universe())),
            "official_fixing_unavailable",
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
        # paused by a cooldown: wait, poll nothing
        if self.runtime.cooldown_seconds_left() > 0:
            return
        # re-read defaults + settlement currencies of open trades
        if (
            time.monotonic() - self._universe_loaded_at
            >= OFFICIAL_FIXING_FEED_UNIVERSE_REFRESH_SECONDS
        ):
            self.reload_universe()
        # window polling until a new as-of appears, else bounded confirmation polls
        if self._last_fetch is None or (
            time.monotonic() - self._last_fetch >= self._retry_interval(utcnow())
        ):
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

    def active_symbols(self):
        return sorted(self.universe())

    def runtime_snapshot(self):
        return {
            **self.runtime.snapshot(self.active_symbols()),
            "strategy": self.poll_strategy(),
        }
