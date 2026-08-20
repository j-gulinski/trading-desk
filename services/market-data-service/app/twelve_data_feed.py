import threading
import time

from shared.functions import utcnow
from shared.logging_config import get_logger
from shared.providers import TWELVE_DATA
from app import persistence
from shared.active_set import load_active_set
from app.clients.base import (
    ProviderAuthError,
    ProviderDataError,
    ProviderError,
    ProviderRateLimited,
)
from app.clients.twelve_data import TwelveDataClient
from app.config import (
    ACTIVE_SET_REFRESH_SECONDS,
    AUTH_FAILURE_COOLDOWN_SECONDS,
    FRESHNESS_THRESHOLD_MULTIPLIER,
    PROVIDER_ACTIVE_WINDOW_SECONDS,
    RATE_LIMIT_DEFAULT_COOLDOWN_SECONDS,
    SERVICE_NAME,
    TRANSIENT_ERROR_BACKOFF_SECONDS,
    TWELVE_DATA_API_KEY,
    TWELVE_DATA_BUDGET_PER_MINUTE,
    TWELVE_DATA_DAILY_BUDGET,
    TWELVE_DATA_POLL_SECONDS,
    TWELVE_DATA_PROVIDER_LIMIT_PER_DAY,
    TWELVE_DATA_PROVIDER_LIMIT_PER_MINUTE,
)
from app.normalizer import normalize_twelve_data_quote
from app.provider_runtime import ProviderRuntime
from app.publisher import publish_quote
from app.quote_audit import audit_first_quote

log = get_logger(SERVICE_NAME)

PROVIDER = TWELVE_DATA
runtime = ProviderRuntime(
    TWELVE_DATA,
    TWELVE_DATA_BUDGET_PER_MINUTE,
    bool(TWELVE_DATA_API_KEY),
    daily_budget=TWELVE_DATA_DAILY_BUDGET,
    provider_minute_limit=TWELVE_DATA_PROVIDER_LIMIT_PER_MINUTE,
    provider_daily_limit=TWELVE_DATA_PROVIDER_LIMIT_PER_DAY,
)
_client = TwelveDataClient(TWELVE_DATA_API_KEY)
_next_due = {}
_market_open_lock = threading.Lock()
_market_open = {}


def paced_interval_seconds():
    symbols = max(1, len(runtime.pollable_entries()))
    return max(
        TWELVE_DATA_POLL_SECONDS,
        round(PROVIDER_ACTIVE_WINDOW_SECONDS * symbols / TWELVE_DATA_DAILY_BUDGET),
    )


def stale_after_seconds(symbol):
    return FRESHNESS_THRESHOLD_MULTIPLIER * paced_interval_seconds()


def closed_stale_after_seconds(symbol):
    return FRESHNESS_THRESHOLD_MULTIPLIER * paced_interval_seconds()


def market_open(symbol):
    with _market_open_lock:
        return _market_open.get(symbol)


def reload_active():
    runtime.set_active(load_active_set())


def _record_market_open(symbol, payload):
    if not isinstance(payload, dict) or "is_market_open" not in payload:
        return
    with _market_open_lock:
        _market_open[symbol] = bool(payload["is_market_open"])


def _pacing_allows(credits_needed):
    return runtime.ledger.credits_today() + credits_needed <= TWELVE_DATA_DAILY_BUDGET


def _classifier(symbol):
    return {
        "stale_after_seconds": stale_after_seconds(symbol),
        "closed_stale_after_seconds": closed_stale_after_seconds(symbol),
        "market_open": market_open(symbol),
    }


def _wire_quote(quote):
    entry = runtime.active_entry(quote.symbol)
    origin = entry.origin(TWELVE_DATA) if entry else {}
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
        **_classifier(quote.symbol),
        "watched": bool(origin.get("watched")),
        "held": bool(origin.get("held")),
        "benchmark": bool(origin.get("benchmark")),
    }


def _store_and_publish(entry, payload):
    _record_market_open(entry.symbol, payload)
    quote = normalize_twelve_data_quote(
        entry.symbol, entry.asset_class, entry.currency, payload, utcnow()
    )
    _, created = persistence.store_quote(quote, _classifier(entry.symbol))
    if created:
        audit_first_quote(TWELVE_DATA, quote)
    tick = _wire_quote(quote)
    publish_quote(tick)
    return tick


def _fetch_and_publish(entries):
    runtime.record_request(credits=len(entries))
    by_provider_symbol = {
        _client.provider_symbol(entry.symbol, entry.asset_class): entry
        for entry in entries
    }
    payload = _client.quotes(list(by_provider_symbol))
    quotes = payload if len(by_provider_symbol) > 1 else {next(iter(by_provider_symbol)): payload}
    ticks = {}
    for provider_symbol, entry in by_provider_symbol.items():
        try:
            ticks[entry.symbol] = _store_and_publish(entry, quotes.get(provider_symbol))
        except ProviderDataError as error:
            log.warning("quote_unavailable", provider=TWELVE_DATA, symbol=entry.symbol,
                        detail=error.detail)
    runtime.record_success()
    return ticks


def _guarded_fetch(entries):
    try:
        return _fetch_and_publish(entries), None
    except ProviderRateLimited as error:
        cooldown = error.retry_after_seconds or RATE_LIMIT_DEFAULT_COOLDOWN_SECONDS
        runtime.enter_cooldown(
            "RATE_LIMITED", "rate limited", error.detail, cooldown,
            "PROVIDER_RATE_LIMITED", "WARNING",
        )
        return None, "TWELVE_DATA is rate limited"
    except ProviderAuthError as error:
        runtime.enter_cooldown(
            "AUTH_FAILED", "authentication failed", error.detail,
            AUTH_FAILURE_COOLDOWN_SECONDS, "PROVIDER_AUTH_FAILED", "ERROR",
        )
        return None, "TWELVE_DATA rejected the API key"
    except ProviderDataError as error:
        log.warning("quote_batch_unavailable", provider=TWELVE_DATA, detail=error.detail)
        return None, error.detail
    except ProviderError as error:
        runtime.transient_error(error.detail, TRANSIENT_ERROR_BACKOFF_SECONDS)
        return None, error.detail


def _prune_next_due(entries):
    keep = {entry.symbol for entry in entries}
    for symbol in list(_next_due):
        if symbol not in keep:
            del _next_due[symbol]


def poll_loop():
    if not TWELVE_DATA_API_KEY:
        log.warning("twelve_data_disabled", reason="TWELVE_DATA_API_KEY is not set")
        return
    last_set_refresh = 0.0
    while True:
        now = time.monotonic()
        if runtime.cooldown_seconds_left() > 0:
            time.sleep(min(runtime.cooldown_seconds_left(), 5))
            continue
        # reload the provider-specific slice of watchlist + positions + benchmark
        if not last_set_refresh or now - last_set_refresh >= ACTIVE_SET_REFRESH_SECONDS:
            try:
                runtime.set_active(load_active_set())
            except Exception:
                log.exception("active_set_load_failed")
                time.sleep(5)
                continue
            last_set_refresh = now
        pollable = runtime.pollable_entries()
        due = sorted(
            (entry for entry in pollable
             if _next_due.get(entry.symbol, 0) <= time.monotonic()),
            key=lambda entry: (entry.tier, entry.symbol),
        )
        # poll due symbols in batches while both the minute and daily budgets allow
        for start in range(0, len(due), TWELVE_DATA_BUDGET_PER_MINUTE):
            chunk = due[start:start + TWELVE_DATA_BUDGET_PER_MINUTE]
            if runtime.cooldown_seconds_left() > 0 or not _pacing_allows(len(chunk)):
                break
            if not runtime.try_take(len(chunk)):
                break
            _guarded_fetch(chunk)
            interval = paced_interval_seconds()
            for entry in chunk:
                _next_due[entry.symbol] = time.monotonic() + interval
        # forget symbols that left this provider's active set
        _prune_next_due(pollable)
        time.sleep(1)


def refresh_symbol(symbol):
    if not TWELVE_DATA_API_KEY:
        return None, "TWELVE_DATA is disabled: no API key configured", 503
    entry = runtime.active_entry(symbol)
    if entry is None:
        runtime.set_active(load_active_set())
        entry = runtime.active_entry(symbol)
    if entry is None:
        return None, "symbol is not in the active set", 404
    if not entry.serves(TWELVE_DATA):
        return None, f"TWELVE_DATA is not watching {symbol}", 422
    cooldown_left = runtime.cooldown_seconds_left()
    if cooldown_left > 0:
        return None, f"TWELVE_DATA is {runtime.status()}: retry in {round(cooldown_left)}s", 503
    if not _pacing_allows(1):
        return None, "TWELVE_DATA daily credit budget is spent for now: retry later", 429
    if not runtime.try_take():
        return None, "TWELVE_DATA request budget is exhausted: retry shortly", 429
    ticks, error = _guarded_fetch([entry])
    tick = (ticks or {}).get(symbol)
    if tick is None:
        http_status = 429 if runtime.status() == "RATE_LIMITED" else 502
        return None, error or f"no quote data for {symbol}", http_status
    _next_due[symbol] = time.monotonic() + paced_interval_seconds()
    return tick, None, 200


def search(query):
    if not TWELVE_DATA_API_KEY or runtime.cooldown_seconds_left() > 0:
        return None
    if not _pacing_allows(1) or not runtime.try_take():
        return None
    runtime.record_request()
    return _client.search(query)


def poll_strategy():
    on_pace = _pacing_allows(1)
    cadence = paced_interval_seconds()
    description = (
        f"batch of ≤{TWELVE_DATA_BUDGET_PER_MINUTE} every "
        f"{cadence // 60} min · {TWELVE_DATA_DAILY_BUDGET} credits over configured "
        f"active window"
    )
    if not on_pace:
        description += " — holding for daily pace"
    return {
        "mode": "BATCHED_DAILY_LEDGER",
        "poll_seconds": TWELVE_DATA_POLL_SECONDS,
        "batch_size": TWELVE_DATA_BUDGET_PER_MINUTE,
        "daily_budget": TWELVE_DATA_DAILY_BUDGET,
        "current_cadence_seconds": cadence,
        "on_pace": on_pace,
        "description": description,
    }


def active_symbols():
    return sorted(entry.symbol for entry in runtime.pollable_entries())


def runtime_snapshot():
    symbols = active_symbols()
    with _market_open_lock:
        states = [_market_open.get(symbol) for symbol in symbols]
    return {
        **runtime.snapshot(symbols),
        "market_states": {
            "open": sum(state is True for state in states),
            "closed": sum(state is False for state in states),
            "unknown": sum(state is None for state in states),
        },
        "strategy": poll_strategy(),
    }
