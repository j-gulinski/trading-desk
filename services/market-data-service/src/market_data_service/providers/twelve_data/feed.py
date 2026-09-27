from desk_domain.providers import TWELVE_DATA

from market_data_service.providers.twelve_data.client import TwelveDataClient
from market_data_service.providers.twelve_data.normalizer import (
    normalize_quote,
    normalize_search_results,
)
from market_data_service.config import (
    FRESHNESS_THRESHOLD_MULTIPLIER,
    PROVIDER_ACTIVE_WINDOW_SECONDS,
    TWELVE_DATA_API_KEY,
    TWELVE_DATA_BUDGET_PER_MINUTE,
    TWELVE_DATA_DAILY_BUDGET,
    TWELVE_DATA_POLL_SECONDS,
    TWELVE_DATA_PROVIDER_LIMIT_PER_DAY,
    TWELVE_DATA_PROVIDER_LIMIT_PER_MINUTE,
    TRANSIENT_ERROR_BACKOFF_SECONDS,
)
from market_data_service.provider_runtime import ProviderRuntime
from market_data_service.symbol_quote_feed import SymbolQuoteFeed


class TwelveDataFeed(SymbolQuoteFeed):
    """Equity, FX and commodity quotes in batches paced to spread the daily credit budget."""

    def __init__(self, *args):
        super().__init__(*args)
        self._market_open = {}

    def fetch(self, entries):
        symbols = {
            self.client.provider_symbol(entry.symbol, entry.asset_class): entry.symbol
            for entry in entries
        }
        payload = self.client.quotes(list(symbols))
        if len(symbols) == 1:
            payload = {next(iter(symbols)): payload}
        payloads = {symbol: payload.get(provider_symbol) for provider_symbol, symbol in symbols.items()}
        for symbol, quote in payloads.items():
            if isinstance(quote, dict) and "is_market_open" in quote:
                self._market_open[symbol] = bool(quote["is_market_open"])
        return payloads

    def normalize(self, entry, payload, received_at):
        return normalize_quote(entry.symbol, entry.asset_class, entry.currency, payload, received_at)

    def _paced_interval(self):
        symbols = max(1, len(self.entries()))
        return max(
            TWELVE_DATA_POLL_SECONDS,
            round(PROVIDER_ACTIVE_WINDOW_SECONDS * symbols / TWELVE_DATA_DAILY_BUDGET),
        )

    def cadence_seconds(self, entry):
        return self._paced_interval()

    def classifier(self, entry):
        stale_after = FRESHNESS_THRESHOLD_MULTIPLIER * self._paced_interval()
        return {
            "stale_after_seconds": stale_after,
            "closed_stale_after_seconds": stale_after,
            "market_open": self._market_open.get(entry.symbol),
        }

    def poll(self, entries):
        ticks, error = super().poll(entries)
        if ticks is None and self.runtime.cooldown_seconds_left() <= 0:
            self.runtime.transient_error(error, TRANSIENT_ERROR_BACKOFF_SECONDS)
        return ticks, error

    def poll_round(self, entries):
        due = self.schedule.due_entries(entries)
        for start in range(0, len(due), TWELVE_DATA_BUDGET_PER_MINUTE):
            chunk = due[start:start + TWELVE_DATA_BUDGET_PER_MINUTE]
            if self.runtime.cooldown_seconds_left() > 0 or self.runtime.acquire(len(chunk)) is not None:
                break
            ticks, _ = self.poll(chunk)
            if ticks is None:
                break
            # spread the chunk's next due-times across the interval
            interval = self._paced_interval()
            for position, entry in enumerate(chunk, start=start):
                self.schedule.defer(entry.symbol, interval + round(position * interval / len(due)))

    def search(self, query):
        payload = self._request(
            lambda: self.client.search(query), "symbol_search_unavailable", query=query,
        )
        return None if payload is None else normalize_search_results(payload)

    def market_states(self, symbols):
        states = [self._market_open.get(symbol) for symbol in symbols]
        return {
            "open": sum(state is True for state in states),
            "closed": sum(state is False for state in states),
            "unknown": sum(state is None for state in states),
        }

    def strategy(self):
        on_pace = self.runtime.budget.credits_left_today() >= 1
        cadence = self._paced_interval()
        entries = self.entries()
        symbols = len(entries)
        due = self.schedule.due_entries(entries)
        next_cost = min(len(due), TWELVE_DATA_BUDGET_PER_MINUTE) if due else 1
        schedule_wait = self.schedule.next_due_seconds(entries)
        next_batch = (
            None if schedule_wait is None
            else max(schedule_wait, self.runtime.budget.wait_seconds(next_cost))
        )
        if next_batch is None:
            description = "no symbols on the daily ledger"
        else:
            description = (
                f"next batch in {next_batch}s · cadence {round(cadence / 60)} min "
                f"({symbols} {'symbol' if symbols == 1 else 'symbols'} on the daily ledger)"
            )
        if not on_pace:
            description += " — holding for daily pace"
        return {
            "mode": "BATCHED_DAILY_LEDGER",
            "poll_seconds": TWELVE_DATA_POLL_SECONDS,
            "batch_size": TWELVE_DATA_BUDGET_PER_MINUTE,
            "daily_budget": TWELVE_DATA_DAILY_BUDGET,
            "current_cadence_seconds": cadence,
            "next_batch_seconds": next_batch,
            "symbol_count": symbols,
            "on_pace": on_pace,
            "description": description,
        }


feed = TwelveDataFeed(
    TWELVE_DATA,
    ProviderRuntime(
        TWELVE_DATA,
        bool(TWELVE_DATA_API_KEY),
        per_minute=TWELVE_DATA_BUDGET_PER_MINUTE,
        per_day=TWELVE_DATA_DAILY_BUDGET,
        provider_minute_limit=TWELVE_DATA_PROVIDER_LIMIT_PER_MINUTE,
        provider_daily_limit=TWELVE_DATA_PROVIDER_LIMIT_PER_DAY,
    ),
    TwelveDataClient(TWELVE_DATA_API_KEY),
)
