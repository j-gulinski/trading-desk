import time

from shared.functions import utcnow
from shared.logging_config import get_logger
from shared.providers import FINNHUB, supports_quotes
from app import persistence
from app.active_set import load_active_set
from app.clients.base import (
    ProviderAuthError,
    ProviderDataError,
    ProviderError,
    ProviderRateLimited,
)
from app.clients.finnhub import FinnhubClient
from app.config import (
    ACTIVE_SET_REFRESH_SECONDS,
    AUTH_FAILURE_COOLDOWN_SECONDS,
    FINNHUB_API_KEY,
    FINNHUB_BUDGET_PER_MINUTE,
    FINNHUB_CLOSED_POLL_SECONDS,
    FINNHUB_TIER1_POLL_SECONDS,
    FINNHUB_TIER2_POLL_SECONDS,
    FRESHNESS_THRESHOLD_MULTIPLIER,
    MARKET_STATUS_REFRESH_SECONDS,
    RATE_LIMIT_DEFAULT_COOLDOWN_SECONDS,
    SERVICE_NAME,
    TRANSIENT_ERROR_BACKOFF_SECONDS,
)
from app.normalizer import normalize_finnhub_quote
from app.provider_runtime import ProviderRuntime
from app.publisher import publish_quote

log = get_logger(SERVICE_NAME)

PROVIDER = FINNHUB
runtime = ProviderRuntime(FINNHUB, FINNHUB_BUDGET_PER_MINUTE, bool(FINNHUB_API_KEY))
_client = FinnhubClient(FINNHUB_API_KEY)
_next_due = {}


def stale_after_seconds(symbol):
    entry = runtime.active_entry(symbol)
    tier1 = entry is not None and entry.tier == 1
    poll = FINNHUB_TIER1_POLL_SECONDS if tier1 else FINNHUB_TIER2_POLL_SECONDS
    return FRESHNESS_THRESHOLD_MULTIPLIER * poll


def _wire_quote(quote):
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
        "provider_timestamp": quote.provider_timestamp,
        "received_at": quote.received_at,
        "event_time": quote.received_at,
        "stale_after_seconds": stale_after_seconds(quote.symbol),
    }


def _fetch_and_publish(entry):
    runtime.record_request()
    payload = _client.quote(entry.symbol)
    quote = normalize_finnhub_quote(
        entry.symbol, entry.asset_class, entry.currency, payload, utcnow()
    )
    persistence.store_quote(quote)
    tick = _wire_quote(quote)
    publish_quote(tick)
    runtime.record_success()
    return tick


def _guarded_fetch(entry):
    try:
        return _fetch_and_publish(entry), None
    except ProviderRateLimited as error:
        cooldown = error.retry_after_seconds or RATE_LIMIT_DEFAULT_COOLDOWN_SECONDS
        runtime.enter_cooldown(
            "RATE_LIMITED", "rate limited", error.detail, cooldown,
            "PROVIDER_RATE_LIMITED", "WARNING",
        )
        return None, "FINNHUB is rate limited"
    except ProviderAuthError as error:
        runtime.enter_cooldown(
            "AUTH_FAILED", "authentication failed", error.detail,
            AUTH_FAILURE_COOLDOWN_SECONDS, "PROVIDER_AUTH_FAILED", "ERROR",
        )
        return None, "FINNHUB rejected the API key"
    except ProviderDataError as error:
        log.warning("quote_unavailable", provider=FINNHUB, symbol=entry.symbol,
                    detail=error.detail)
        return None, error.detail
    except ProviderError as error:
        runtime.transient_error(error.detail, TRANSIENT_ERROR_BACKOFF_SECONDS)
        return None, error.detail


def _refresh_market_status():
    if not runtime.try_take():
        return
    runtime.record_request()
    try:
        payload = _client.market_status()
    except ProviderError as error:
        log.warning("market_status_failed", provider=FINNHUB, detail=error.detail)
        return
    runtime.set_market_status(bool(payload.get("isOpen")), payload.get("session"))
    log.info("market_status", provider=FINNHUB, is_open=bool(payload.get("isOpen")),
             session=payload.get("session"))


def _cadence_seconds(tier):
    if runtime.market_open() is False:
        return FINNHUB_CLOSED_POLL_SECONDS
    return FINNHUB_TIER1_POLL_SECONDS if tier == 1 else FINNHUB_TIER2_POLL_SECONDS


def _prune_next_due(entries):
    keep = {entry.symbol for entry in entries}
    for symbol in list(_next_due):
        if symbol not in keep:
            del _next_due[symbol]


def poll_loop():
    if not FINNHUB_API_KEY:
        log.warning("finnhub_disabled", reason="FINNHUB_API_KEY is not set")
        return
    last_set_refresh = 0.0
    last_status_refresh = 0.0
    while True:
        now = time.monotonic()
        # paused by a cooldown: wait, poll nothing
        if runtime.cooldown_seconds_left() > 0:
            time.sleep(min(runtime.cooldown_seconds_left(), 5))
            continue
        # reload which symbols to poll: watchlist + open trades + benchmark
        if not last_set_refresh or now - last_set_refresh >= ACTIVE_SET_REFRESH_SECONDS:
            try:
                runtime.set_active(load_active_set())
            except Exception:
                log.exception("active_set_load_failed")
                time.sleep(5)
                continue
            last_set_refresh = now
        # re-check whether the US market is open
        if not last_status_refresh or now - last_status_refresh >= MARKET_STATUS_REFRESH_SECONDS:
            _refresh_market_status()
            last_status_refresh = now
        # collect due symbols Finnhub can serve, tier 1 first
        pollable = [
            entry for entry in runtime.active_entries()
            if supports_quotes(FINNHUB, entry.asset_class)
        ]
        due = sorted(
            (entry for entry in pollable
             if _next_due.get(entry.symbol, 0) <= time.monotonic()),
            key=lambda entry: (entry.tier, entry.symbol),
        )
        # poll while budget lasts: an empty bucket ends the round, symbols stay due
        for entry in due:
            if runtime.cooldown_seconds_left() > 0 or not runtime.try_take():
                break
            _guarded_fetch(entry)
            _next_due[entry.symbol] = time.monotonic() + _cadence_seconds(entry.tier)
        # forget symbols that left the active set
        _prune_next_due(pollable)
        time.sleep(1)


def refresh_symbol(symbol):
    """Returns (tick, error, http_status)."""
    # eligibility: key configured, symbol active, asset class supported
    if not FINNHUB_API_KEY:
        return None, "FINNHUB is disabled: no API key configured", 503
    entry = runtime.active_entry(symbol)
    if entry is None:
        runtime.set_active(load_active_set())
        entry = runtime.active_entry(symbol)
    if entry is None:
        return None, "symbol is not in the active set", 404
    if not supports_quotes(FINNHUB, entry.asset_class):
        return None, f"FINNHUB does not serve {entry.asset_class}", 422
    # capacity: no cooldown running, one token available
    cooldown_left = runtime.cooldown_seconds_left()
    if cooldown_left > 0:
        return None, f"FINNHUB is {runtime.status()}: retry in {round(cooldown_left)}s", 503
    if not runtime.try_take():
        return None, "FINNHUB request budget is exhausted: retry shortly", 429
    # same poll as the loop, then push the scheduled poll out
    tick, error = _guarded_fetch(entry)
    if tick is None:
        http_status = 429 if runtime.status() == "RATE_LIMITED" else 502
        return None, error, http_status
    _next_due[symbol] = time.monotonic() + _cadence_seconds(entry.tier)
    return tick, None, 200


def runtime_snapshot():
    return runtime.snapshot(
        sorted(
            entry.symbol
            for entry in runtime.active_entries()
            if supports_quotes(FINNHUB, entry.asset_class)
        )
    )
