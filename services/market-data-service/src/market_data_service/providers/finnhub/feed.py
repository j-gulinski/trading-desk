import time

from desk_runtime.logging_config import get_logger
from desk_domain.providers import FINNHUB

from market_data_service.providers.finnhub.client import FinnhubClient
from market_data_service.providers.finnhub.normalizer import normalize_quote, normalize_search_results
from market_data_service.config import (
    FINNHUB_API_KEY,
    FINNHUB_BUDGET_PER_MINUTE,
    FINNHUB_PROVIDER_LIMIT_PER_MINUTE,
    FINNHUB_CLOSED_POLL_SECONDS,
    FINNHUB_MARKET_STATUS_REFRESH_SECONDS,
    FINNHUB_POLL_CONCURRENCY,
    FINNHUB_PROVIDER_CLOCK_LAG_SECONDS,
    FINNHUB_TIER1_POLL_SECONDS,
    FINNHUB_TIER2_POLL_SECONDS,
    FRESHNESS_THRESHOLD_MULTIPLIER,
    SERVICE_NAME,
)
from market_data_service.provider_runtime import ProviderRuntime
from market_data_service.symbol_quote_feed import SymbolQuoteFeed

log = get_logger(SERVICE_NAME)


def _tier_seconds(entry):
    return FINNHUB_TIER1_POLL_SECONDS if entry.tier == 1 else FINNHUB_TIER2_POLL_SECONDS


class FinnhubFeed(SymbolQuoteFeed):
    """US equity quotes on tier cadences, slowed down while the US market is closed."""

    poll_concurrency = FINNHUB_POLL_CONCURRENCY

    def __init__(self, *args):
        super().__init__(*args)
        self._status_checked_at = None

    def fetch(self, entries):
        return {entry.symbol: self.client.quote(entry.symbol) for entry in entries}

    def normalize(self, entry, payload, received_at):
        return normalize_quote(entry.symbol, entry.asset_class, entry.currency, payload, received_at)

    def before_round(self, entries):
        now = time.monotonic()
        if (
            self._status_checked_at is not None
            and now - self._status_checked_at < FINNHUB_MARKET_STATUS_REFRESH_SECONDS
        ):
            return
        self._status_checked_at = now
        payload = self._request(self.client.market_status, "market_status_failed")
        if payload is None:
            return
        is_open, session = bool(payload.get("isOpen")), payload.get("session")
        self.runtime.set_market_status(is_open, session)
        log.info("market_status", provider=FINNHUB, is_open=is_open, session=session)

    def cadence_seconds(self, entry):
        if self.runtime.market_open() is False:
            return FINNHUB_CLOSED_POLL_SECONDS
        return _tier_seconds(entry)

    def classifier(self, entry):
        return {
            "stale_after_seconds": FRESHNESS_THRESHOLD_MULTIPLIER * _tier_seconds(entry)
            + FINNHUB_PROVIDER_CLOCK_LAG_SECONDS,
            "closed_stale_after_seconds": FRESHNESS_THRESHOLD_MULTIPLIER * FINNHUB_CLOSED_POLL_SECONDS,
            "market_open": self.runtime.market_open(),
        }

    def search(self, query):
        payload = self._request(
            lambda: self.client.search(query), "symbol_search_unavailable", query=query,
        )
        return None if payload is None else normalize_search_results(payload)

    def market_states(self, symbols):
        is_open = self.runtime.market_open()
        return {
            "open": len(symbols) if is_open is True else 0,
            "closed": len(symbols) if is_open is False else 0,
            "unknown": len(symbols) if is_open is None else 0,
        }

    def strategy(self):
        closed = self.runtime.market_open() is False
        if closed:
            description = (
                f"market closed — confirmation poll every {FINNHUB_CLOSED_POLL_SECONDS} s "
                f"({FINNHUB_TIER1_POLL_SECONDS} s / {FINNHUB_TIER2_POLL_SECONDS} s when open)"
            )
        else:
            description = (
                f"every {FINNHUB_TIER1_POLL_SECONDS} s tier 1 (open trades + benchmark) · "
                f"every {FINNHUB_TIER2_POLL_SECONDS} s watchlist"
            )
        return {
            "mode": "TIERED",
            "tier1_seconds": FINNHUB_TIER1_POLL_SECONDS,
            "tier2_seconds": FINNHUB_TIER2_POLL_SECONDS,
            "closed_seconds": FINNHUB_CLOSED_POLL_SECONDS,
            "current_cadence_seconds": FINNHUB_CLOSED_POLL_SECONDS if closed
            else FINNHUB_TIER1_POLL_SECONDS,
            "description": description,
        }


feed = FinnhubFeed(
    FINNHUB,
    ProviderRuntime(
        FINNHUB,
        bool(FINNHUB_API_KEY),
        per_minute=FINNHUB_BUDGET_PER_MINUTE,
        provider_minute_limit=FINNHUB_PROVIDER_LIMIT_PER_MINUTE,
    ),
    FinnhubClient(FINNHUB_API_KEY),
)
