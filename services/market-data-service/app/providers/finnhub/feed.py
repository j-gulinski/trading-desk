import time

from shared.active_set import load_active_set
from shared.functions import utcnow
from shared.logging_config import get_logger
from shared.providers import FINNHUB
from shared.quotes import wire_tick
from app import quote_lifecycle, quote_store
from app.providers.base import ProviderDataError
from app.providers.finnhub.client import FinnhubClient
from app.providers.finnhub.normalizer import normalize_quote
from app.config import (
    FINNHUB_API_KEY,
    FINNHUB_BUDGET_PER_MINUTE,
    FINNHUB_PROVIDER_LIMIT_PER_MINUTE,
    FINNHUB_CLOSED_POLL_SECONDS,
    FINNHUB_MARKET_STATUS_REFRESH_SECONDS,
    FINNHUB_PROVIDER_CLOCK_LAG_SECONDS,
    FINNHUB_TIER1_POLL_SECONDS,
    FINNHUB_TIER2_POLL_SECONDS,
    FRESHNESS_THRESHOLD_MULTIPLIER,
    SERVICE_NAME,
)
from app.poll_schedule import PollSchedule
from app.provider_runtime import ProviderRuntime
from app.publisher import publish_quote
from app.quote_audit import audit_first_quote

log = get_logger(SERVICE_NAME)

PROVIDER = FINNHUB
runtime = ProviderRuntime(
    FINNHUB,
    FINNHUB_BUDGET_PER_MINUTE,
    bool(FINNHUB_API_KEY),
    provider_minute_limit=FINNHUB_PROVIDER_LIMIT_PER_MINUTE,
)
_client = FinnhubClient(FINNHUB_API_KEY)
_schedule = PollSchedule()


def _cadence_seconds(tier):
    if runtime.market_open() is False:
        return FINNHUB_CLOSED_POLL_SECONDS
    return FINNHUB_TIER1_POLL_SECONDS if tier == 1 else FINNHUB_TIER2_POLL_SECONDS


def stale_after_seconds(symbol):
    entry = runtime.active_entry(symbol)
    tier = entry.tier if entry is not None else 2
    poll = FINNHUB_TIER1_POLL_SECONDS if tier == 1 else FINNHUB_TIER2_POLL_SECONDS
    return FRESHNESS_THRESHOLD_MULTIPLIER * poll + FINNHUB_PROVIDER_CLOCK_LAG_SECONDS


def closed_stale_after_seconds(symbol):
    return FRESHNESS_THRESHOLD_MULTIPLIER * FINNHUB_CLOSED_POLL_SECONDS


def market_open(symbol):
    return runtime.market_open()


reload_active = runtime.reload_active


def _classifier(symbol):
    return {
        "stale_after_seconds": stale_after_seconds(symbol),
        "closed_stale_after_seconds": closed_stale_after_seconds(symbol),
        "market_open": runtime.market_open(),
    }


def _fetch_and_publish(entry):
    runtime.record_request()
    payload = _client.quote(entry.symbol)
    with quote_lifecycle.locked_keys(entry.symbol, (FINNHUB,)):
        current = load_active_set().get(entry.symbol)
        if current is None or not current.serves(FINNHUB):
            raise ProviderDataError(
                FINNHUB, f"{entry.symbol} left the FINNHUB active set during refresh"
            )
        quote = normalize_quote(
            current.symbol, current.asset_class, current.currency, payload, utcnow()
        )
        classifier = _classifier(current.symbol)
        _, created, accepted = quote_store.store_quote(quote, classifier)
        if not accepted:
            raise ProviderDataError(
                FINNHUB,
                f"older observation for {current.symbol} ignored; current row retained",
            )
        if created:
            audit_first_quote(FINNHUB, quote)
        tick = wire_tick(quote, classifier, current.origin(FINNHUB))
        publish_quote(tick)
    runtime.record_success()
    return tick


def _guarded_fetch(entry):
    return runtime.guarded(
        lambda: _fetch_and_publish(entry), "quote_unavailable",
        log_level="warning", symbol=entry.symbol,
    )


def _refresh_market_status():
    if not runtime.try_take():
        return

    def fetch():
        runtime.record_request()
        payload = _client.market_status()
        runtime.record_success()
        return payload

    payload, _ = runtime.guarded(
        fetch, "market_status_failed", log_level="warning"
    )
    if payload is None:
        return
    runtime.set_market_status(bool(payload.get("isOpen")), payload.get("session"))
    log.info("market_status", provider=FINNHUB, is_open=bool(payload.get("isOpen")),
             session=payload.get("session"))


def poll_loop():
    if not FINNHUB_API_KEY:
        log.warning("finnhub_disabled", reason="FINNHUB_API_KEY is not set")
        return
    last_status_refresh = 0.0
    while True:
        # paused by a cooldown: wait, poll nothing
        if runtime.cooldown_seconds_left() > 0:
            time.sleep(min(runtime.cooldown_seconds_left(), 5))
            continue
        # reload which symbols to poll: watchlist + open trades + benchmark
        if not runtime.reload_active_if_stale():
            time.sleep(5)
            continue
        # re-check whether the US market is open
        now = time.monotonic()
        if (
            not last_status_refresh
            or now - last_status_refresh >= FINNHUB_MARKET_STATUS_REFRESH_SECONDS
        ):
            _refresh_market_status()
            last_status_refresh = now
        pollable = runtime.pollable_entries()
        # poll while budget lasts: an empty bucket ends the round, symbols stay due
        for entry in _schedule.due_entries(pollable):
            if runtime.cooldown_seconds_left() > 0 or not runtime.try_take():
                break
            _guarded_fetch(entry)
            _schedule.defer(entry.symbol, _cadence_seconds(entry.tier))
        _schedule.keep_only(pollable)
        time.sleep(1)


def refresh_symbol(symbol):
    """Returns (tick, error, http_status)."""
    if not FINNHUB_API_KEY:
        return None, "FINNHUB is disabled: no API key configured", 503
    entry, error, status = runtime.resolve(symbol)
    if error is not None:
        return None, error, status
    unavailable = runtime.unavailable()
    if unavailable is not None:
        return None, unavailable, 503
    if not runtime.try_take():
        return None, "FINNHUB request budget is exhausted: retry shortly", 429
    # same poll as the loop, then push the scheduled poll out
    tick, error = _guarded_fetch(entry)
    if tick is None:
        return None, error, 429 if runtime.status() == "RATE_LIMITED" else 502
    _schedule.defer(symbol, _cadence_seconds(entry.tier))
    return tick, None, 200


def search(query):
    if not FINNHUB_API_KEY or runtime.cooldown_seconds_left() > 0:
        return None
    if not runtime.try_take():
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
    closed = runtime.market_open() is False
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


def active_symbols():
    return sorted(entry.symbol for entry in runtime.pollable_entries())


def runtime_snapshot():
    symbols = active_symbols()
    is_open = runtime.market_open()
    return {
        **runtime.snapshot(symbols),
        "market_states": {
            "open": len(symbols) if is_open is True else 0,
            "closed": len(symbols) if is_open is False else 0,
            "unknown": len(symbols) if is_open is None else 0,
        },
        "strategy": poll_strategy(),
    }
