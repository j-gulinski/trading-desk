import time
from abc import ABC, abstractmethod

from desk_runtime.functions import utcnow
from desk_runtime.logging_config import get_logger
from market_data_service import quote_board
from market_data_service.config import SERVICE_NAME
from market_data_service.providers.base import ProviderDataError

log = get_logger(SERVICE_NAME)


class PollSchedule:
    """When each symbol is next due. Tier 1 (open trades, benchmark) polls first."""

    def __init__(self):
        self._due = {}

    def due_entries(self, entries):
        now = time.monotonic()
        return sorted(
            (entry for entry in entries if self._due.get(entry.symbol, 0) <= now),
            key=lambda entry: (entry.tier, entry.symbol),
        )

    def defer(self, symbol, seconds):
        self._due[symbol] = time.monotonic() + seconds

    def next_due_seconds(self, entries):
        due = [self._due.get(entry.symbol, 0) for entry in entries]
        return None if not due else max(0, round(min(due) - time.monotonic()))

    def keep_only(self, entries):
        keep = {entry.symbol for entry in entries}
        for symbol in list(self._due):
            if symbol not in keep:
                del self._due[symbol]


class SymbolQuoteFeed(ABC):
    """Polls one provider for every watchlist, open-trade and benchmark symbol it serves."""

    def __init__(self, provider, runtime, client):
        self.provider = provider
        self.runtime = runtime
        self.client = client
        self.enabled = runtime.enabled
        self.schedule = PollSchedule()

    @abstractmethod
    def fetch(self, entries):
        """Provider payloads by symbol, from one request."""

    @abstractmethod
    def normalize(self, entry, payload, received_at):
        """The desk quote in one provider payload."""

    @abstractmethod
    def cadence_seconds(self, entry):
        """Seconds until a polled symbol is due again."""

    @abstractmethod
    def classifier(self, entry):
        """Freshness fields stored and published with the symbol's quotes."""

    @abstractmethod
    def strategy(self):
        """The polling plan shown on the providers page."""

    def retry_seconds(self, entry):
        return self.cadence_seconds(entry)

    def before_round(self, entries):
        pass

    def market_states(self, symbols):
        return {"open": 0, "closed": 0, "unknown": len(symbols)}

    def entries(self):
        return quote_board.entries_for(self.provider)

    def active_symbols(self):
        return sorted(entry.symbol for entry in self.entries())

    def poll_loop(self):
        if not self.enabled:
            log.warning("quote_feed_disabled", provider=self.provider, reason="API key is not set")
            return
        while True:
            try:
                self._poll_tick()
            except Exception:
                log.exception("quote_feed_tick_failed", provider=self.provider)
                time.sleep(5)
            time.sleep(1)

    def _poll_tick(self):
        # paused by a cooldown: poll nothing
        if self.runtime.cooldown_seconds_left() > 0:
            return
        # symbols served now: watchlist + open trades + benchmark
        quote_board.reload_if_stale()
        entries = self.entries()
        self.before_round(entries)
        # poll due symbols while the budget allows; the rest stay due
        self.poll_round(entries)
        self.schedule.keep_only(entries)

    def poll_round(self, entries):
        for entry in self.schedule.due_entries(entries):
            if self.runtime.cooldown_seconds_left() > 0 or self.runtime.acquire() is not None:
                break
            ticks, _ = self.poll([entry])
            self.schedule.defer(
                entry.symbol,
                self.cadence_seconds(entry) if ticks else self.retry_seconds(entry),
            )

    def poll(self, entries):
        """Fetches, stores and publishes quotes; returns ({symbol: tick} or None, error)."""
        return self.runtime.guarded(
            lambda: self._fetch_and_store(entries), "quote_unavailable", log_level="warning",
            symbols=[entry.symbol for entry in entries],
        )

    def _fetch_and_store(self, entries):
        payloads = self.fetch(entries)
        received_at = utcnow()
        ticks, errors = {}, {}
        for entry in entries:
            try:
                quote = self.normalize(entry, payloads.get(entry.symbol), received_at)
                ticks[entry.symbol] = quote_board.store_and_publish(quote, self.classifier(entry))
            except ProviderDataError as error:
                errors[entry.symbol] = error.detail
            except (ArithmeticError, TypeError, ValueError) as error:
                errors[entry.symbol] = f"invalid provider quote: {type(error).__name__}"
        if not ticks:
            raise ProviderDataError(self.provider, "; ".join(errors.values()))
        for symbol, detail in errors.items():
            log.warning("quote_unavailable", provider=self.provider, symbol=symbol, detail=detail)
        self.runtime.record_success()
        return ticks

    def _request(self, call, event, **context):
        """One budgeted provider call outside the poll round; returns its payload or None."""
        if not self.enabled or self.runtime.cooldown_seconds_left() > 0:
            return None
        if self.runtime.acquire() is not None:
            return None
        payload, _ = self.runtime.guarded(call, event, log_level="warning", **context)
        if payload is not None:
            self.runtime.record_success()
        return payload

    def refresh_symbol(self, symbol):
        """Polls one symbol now; returns (tick, error, http_status)."""
        if not self.enabled:
            return None, f"{self.provider} is disabled: no API key configured", 503
        entry = quote_board.active_entry(symbol)
        if entry is None:
            quote_board.reload()
            entry = quote_board.active_entry(symbol)
        if entry is None:
            return None, "symbol is not in the active set", 404
        if not entry.serves(self.provider):
            return None, f"{self.provider} is not watching {symbol}", 422
        unavailable = self.runtime.unavailable()
        if unavailable is not None:
            return None, unavailable, 503
        refusal = self.runtime.acquire()
        if refusal is not None:
            return None, refusal, 429
        ticks, error = self.poll([entry])
        if ticks is None:
            return None, error, 429 if self.runtime.status() == "RATE_LIMITED" else 502
        self.schedule.defer(symbol, self.cadence_seconds(entry))
        return ticks[symbol], None, 200

    def refresh_all(self):
        """Polls every served symbol now; returns (refreshed, skipped)."""
        refreshed, skipped = [], []
        for symbol in self.active_symbols():
            _, error, _ = self.refresh_symbol(symbol)
            if error is None:
                refreshed.append({"provider": self.provider, "symbol": symbol})
            else:
                skipped.append({"provider": self.provider, "symbol": symbol, "reason": error})
        return refreshed, skipped

    def runtime_snapshot(self):
        symbols = self.active_symbols()
        return {
            **self.runtime.snapshot(symbols),
            "market_states": self.market_states(symbols),
            "strategy": self.strategy(),
        }
