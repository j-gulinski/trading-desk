import threading
import time

from shared.active_set import load_active_set
from shared.functions import utcnow
from shared.logging_config import get_logger
from shared.providers import TWELVE_DATA
from shared.quotes import wire_tick
from app import quote_lifecycle, quote_store
from app.providers.base import ProviderDataError
from app.providers.twelve_data.client import TwelveDataClient
from app.providers.twelve_data.normalizer import normalize_quote
from app.config import (
    FRESHNESS_THRESHOLD_MULTIPLIER,
    PROVIDER_ACTIVE_WINDOW_SECONDS,
    SERVICE_NAME,
    TWELVE_DATA_API_KEY,
    TWELVE_DATA_BUDGET_PER_MINUTE,
    TWELVE_DATA_DAILY_BUDGET,
    TWELVE_DATA_POLL_SECONDS,
    TWELVE_DATA_PROVIDER_LIMIT_PER_DAY,
    TWELVE_DATA_PROVIDER_LIMIT_PER_MINUTE,
    TRANSIENT_ERROR_BACKOFF_SECONDS,
)
from app.poll_schedule import PollSchedule
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
_schedule = PollSchedule()
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


closed_stale_after_seconds = stale_after_seconds


def market_open(symbol):
    with _market_open_lock:
        return _market_open.get(symbol)


reload_active = runtime.reload_active


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


def _store_and_publish(entry, payload):
    with quote_lifecycle.locked_keys(entry.symbol, (TWELVE_DATA,)):
        current = load_active_set().get(entry.symbol)
        if current is None or not current.serves(TWELVE_DATA):
            raise ProviderDataError(
                TWELVE_DATA,
                f"{entry.symbol} left the TWELVE_DATA active set during refresh",
            )
        _record_market_open(current.symbol, payload)
        quote = normalize_quote(
            current.symbol, current.asset_class, current.currency, payload, utcnow()
        )
        classifier = _classifier(current.symbol)
        _, created, accepted = quote_store.store_quote(quote, classifier)
        if not accepted:
            raise ProviderDataError(
                TWELVE_DATA,
                f"older observation for {current.symbol} ignored; current row retained",
            )
        if created:
            audit_first_quote(TWELVE_DATA, quote)
        tick = wire_tick(quote, classifier, current.origin(TWELVE_DATA))
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
        except (ArithmeticError, OverflowError, TypeError, ValueError) as error:
            log.warning(
                "quote_unavailable",
                provider=TWELVE_DATA,
                symbol=entry.symbol,
                detail=f"invalid provider quote: {type(error).__name__}",
            )
    if not ticks:
        raise ProviderDataError(
            TWELVE_DATA, "the quote batch contained no usable observations"
        )
    runtime.record_success()
    return ticks


def _guarded_fetch(entries):
    def fetch():
        try:
            return _fetch_and_publish(entries)
        except ProviderDataError as error:
            # Per-symbol failures are isolated inside _fetch_and_publish. Reaching
            # this boundary means the complete requested batch was unusable.
            runtime.transient_error(error.detail, TRANSIENT_ERROR_BACKOFF_SECONDS)
            raise

    return runtime.guarded(
        fetch, "quote_batch_unavailable",
        log_level="warning",
    )


def poll_loop():
    if not TWELVE_DATA_API_KEY:
        log.warning("twelve_data_disabled", reason="TWELVE_DATA_API_KEY is not set")
        return
    while True:
        if runtime.cooldown_seconds_left() > 0:
            time.sleep(min(runtime.cooldown_seconds_left(), 5))
            continue
        # reload the provider-specific slice of watchlist + positions + benchmark
        if not runtime.reload_active_if_stale():
            time.sleep(5)
            continue
        pollable = runtime.pollable_entries()
        due = _schedule.due_entries(pollable)
        # poll due symbols in batches while both the minute and daily budgets allow
        for start in range(0, len(due), TWELVE_DATA_BUDGET_PER_MINUTE):
            chunk = due[start:start + TWELVE_DATA_BUDGET_PER_MINUTE]
            if runtime.cooldown_seconds_left() > 0 or not _pacing_allows(len(chunk)):
                break
            if not runtime.try_take(len(chunk)):
                break
            ticks, _ = _guarded_fetch(chunk)
            if ticks is None:
                # Keep the symbols due so the short runtime backoff, rather than the
                # normal daily-ledger cadence, controls the retry.
                break
            # spread the polled chunk's next due-times across the interval
            interval = paced_interval_seconds()
            for position, entry in enumerate(chunk, start=start):
                _schedule.defer(entry.symbol, interval + round(position * interval / len(due)))
        _schedule.keep_only(pollable)
        time.sleep(1)


def refresh_symbol(symbol):
    if not TWELVE_DATA_API_KEY:
        return None, "TWELVE_DATA is disabled: no API key configured", 503
    entry, error, status = runtime.resolve(symbol)
    if error is not None:
        return None, error, status
    unavailable = runtime.unavailable()
    if unavailable is not None:
        return None, unavailable, 503
    if not _pacing_allows(1):
        return None, "TWELVE_DATA daily credit budget is spent for now: retry later", 429
    if not runtime.try_take():
        return None, "TWELVE_DATA request budget is exhausted: retry shortly", 429
    ticks, error = _guarded_fetch([entry])
    tick = (ticks or {}).get(symbol)
    if tick is None:
        return None, error or f"no quote data for {symbol}", (
            429 if runtime.status() == "RATE_LIMITED" else 502
        )
    _schedule.defer(symbol, paced_interval_seconds())
    return tick, None, 200


def search(query):
    if not TWELVE_DATA_API_KEY or runtime.cooldown_seconds_left() > 0:
        return None
    if not _pacing_allows(1) or not runtime.try_take():
        return None
    def fetch():
        runtime.record_request()
        payload = _client.search(query)
        runtime.record_success()
        return payload

    payload, _ = runtime.guarded(
        fetch, "symbol_search_unavailable", log_level="warning", query=query
    )
    return payload


def poll_strategy():
    on_pace = _pacing_allows(1)
    cadence = paced_interval_seconds()
    entries = runtime.pollable_entries()
    symbols = len(entries)
    due = _schedule.due_entries(entries)
    next_cost = min(len(due), TWELVE_DATA_BUDGET_PER_MINUTE) if due else 1
    schedule_wait = _schedule.next_due_seconds(entries)
    budget_wait = runtime.budget_wait_seconds(next_cost)
    next_batch = (
        None if schedule_wait is None
        else max(schedule_wait, budget_wait or 0)
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
