from datetime import timedelta
from zoneinfo import ZoneInfo

from market_data_service import quote_store
from market_data_service.config import (
    ALPHA_VANTAGE_API_KEY,
    ALPHA_VANTAGE_DAILY_BUDGET,
    ALPHA_VANTAGE_EQUITY_STALE_SECONDS,
    ALPHA_VANTAGE_FX_POLL_SECONDS,
    ALPHA_VANTAGE_FX_STALE_SECONDS,
    ALPHA_VANTAGE_MIN_REQUEST_INTERVAL_SECONDS,
    ALPHA_VANTAGE_PROVIDER_LIMIT_PER_DAY,
)
from market_data_service.provider_runtime import ProviderRuntime
from market_data_service.providers.alpha_vantage.client import AlphaVantageClient
from market_data_service.providers.alpha_vantage.normalizer import normalize_quote
from market_data_service.symbol_quote_feed import SymbolQuoteFeed
from desk_runtime.functions import utcnow
from desk_domain.providers import ALPHA_VANTAGE

FAILED_RETRY_SECONDS = 300


def _next_equity_refresh_seconds():
    now = utcnow()
    local_now = now.astimezone(ZoneInfo("America/New_York"))
    target = local_now.replace(hour=16, minute=30, second=0, microsecond=0)
    if local_now >= target:
        target += timedelta(days=1)
    while target.weekday() >= 5:
        target += timedelta(days=1)
    return max(60, round((target.astimezone(now.tzinfo) - now).total_seconds()))


def _stale_after_seconds(entry):
    if entry.asset_class == "EQUITY":
        return ALPHA_VANTAGE_EQUITY_STALE_SECONDS
    return ALPHA_VANTAGE_FX_STALE_SECONDS


class AlphaVantageFeed(SymbolQuoteFeed):
    """US equity end-of-day and FX quotes on a small daily budget with spaced requests."""

    def __init__(self, *args):
        super().__init__(*args)
        self._known_symbols = set()

    def fetch(self, entries):
        return {entry.symbol: self.client.quote(entry.symbol, entry.asset_class) for entry in entries}

    def normalize(self, entry, payload, received_at):
        return normalize_quote(entry.symbol, entry.asset_class, entry.currency, payload, received_at)

    def cadence_seconds(self, entry):
        if entry.asset_class == "EQUITY":
            return _next_equity_refresh_seconds()
        return ALPHA_VANTAGE_FX_POLL_SECONDS

    def retry_seconds(self, entry):
        return FAILED_RETRY_SECONDS

    def classifier(self, entry):
        stale_after = _stale_after_seconds(entry)
        return {
            "stale_after_seconds": stale_after,
            "closed_stale_after_seconds": stale_after,
            "market_open": None,
        }

    def before_round(self, entries):
        """Resumes the schedule of newly served symbols from their stored quotes."""
        self._known_symbols.intersection_update(entry.symbol for entry in entries)
        now = utcnow()
        latest_received_at = None
        for entry in entries:
            if entry.symbol in self._known_symbols:
                continue
            self._known_symbols.add(entry.symbol)
            provider_at, received_at = quote_store.quote_clocks(ALPHA_VANTAGE, entry.symbol)
            if provider_at is None or received_at is None:
                continue
            if (now - provider_at).total_seconds() > _stale_after_seconds(entry):
                continue
            if latest_received_at is None or received_at > latest_received_at:
                latest_received_at = received_at
            if entry.asset_class == "EQUITY":
                self.schedule.defer(entry.symbol, _next_equity_refresh_seconds())
            else:
                age = max(0, (now - received_at).total_seconds())
                self.schedule.defer(entry.symbol, max(60, ALPHA_VANTAGE_FX_POLL_SECONDS - age))
        if latest_received_at is not None:
            self.runtime.restore_success(latest_received_at.isoformat())

    def strategy(self):
        entries = self.entries()
        equities = sum(entry.asset_class == "EQUITY" for entry in entries)
        fx = sum(entry.asset_class == "FX" for entry in entries)
        return {
            "mode": "PERSISTED_DAILY_LEDGER",
            "daily_budget": ALPHA_VANTAGE_DAILY_BUDGET,
            "equity_grade": "EOD",
            "fx_poll_seconds": ALPHA_VANTAGE_FX_POLL_SECONDS,
            "next_batch_seconds": self.schedule.next_due_seconds(entries),
            "symbol_count": len(entries),
            "description": (
                f"US equities once after session · FX at most twice daily · "
                f"{equities} EOD / {fx} FX on a persisted "
                f"{ALPHA_VANTAGE_DAILY_BUDGET}-call ledger"
            ),
        }


feed = AlphaVantageFeed(
    ALPHA_VANTAGE,
    ProviderRuntime(
        ALPHA_VANTAGE,
        bool(ALPHA_VANTAGE_API_KEY),
        per_day=ALPHA_VANTAGE_DAILY_BUDGET,
        min_interval_seconds=ALPHA_VANTAGE_MIN_REQUEST_INTERVAL_SECONDS,
        provider_daily_limit=ALPHA_VANTAGE_PROVIDER_LIMIT_PER_DAY,
    ),
    AlphaVantageClient(ALPHA_VANTAGE_API_KEY),
)
