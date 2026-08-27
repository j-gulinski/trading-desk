import threading
import time
from datetime import timedelta
from zoneinfo import ZoneInfo

from app import quote_lifecycle, quote_store
from app.config import (
    ALPHA_VANTAGE_API_KEY,
    ALPHA_VANTAGE_DAILY_BUDGET,
    ALPHA_VANTAGE_EQUITY_STALE_SECONDS,
    ALPHA_VANTAGE_FX_POLL_SECONDS,
    ALPHA_VANTAGE_FX_STALE_SECONDS,
    ALPHA_VANTAGE_MIN_REQUEST_INTERVAL_SECONDS,
    ALPHA_VANTAGE_PROVIDER_LIMIT_PER_DAY,
    SERVICE_NAME,
)
from app.poll_schedule import PollSchedule
from app.provider_runtime import ProviderRuntime
from app.providers.alpha_vantage.client import AlphaVantageClient
from app.providers.alpha_vantage.normalizer import normalize_quote
from app.providers.base import ProviderDataError
from app.publisher import publish_quote
from app.quote_audit import audit_quote_write
from shared.active_set import load_active_set
from shared.functions import utcnow
from shared.logging_config import get_logger
from shared.providers import ALPHA_VANTAGE
from shared.quotes import wire_tick


log = get_logger(SERVICE_NAME)
PROVIDER = ALPHA_VANTAGE
runtime = ProviderRuntime(
    ALPHA_VANTAGE,
    None,
    bool(ALPHA_VANTAGE_API_KEY),
    daily_budget=ALPHA_VANTAGE_DAILY_BUDGET,
    provider_daily_limit=ALPHA_VANTAGE_PROVIDER_LIMIT_PER_DAY,
    persisted_daily_ledger=True,
    min_request_interval_seconds=ALPHA_VANTAGE_MIN_REQUEST_INTERVAL_SECONDS,
)
_client = AlphaVantageClient(ALPHA_VANTAGE_API_KEY)
_schedule = PollSchedule()
_request_lock = threading.Lock()
_known_symbols = set()


def _next_equity_refresh_seconds():
    now = utcnow()
    eastern = ZoneInfo("America/New_York")
    local_now = now.astimezone(eastern)
    target = local_now.replace(hour=16, minute=30, second=0, microsecond=0)
    if local_now >= target:
        target += timedelta(days=1)
    while target.weekday() >= 5:
        target += timedelta(days=1)
    return max(60, round((target.astimezone(now.tzinfo) - now).total_seconds()))


def _cadence_seconds(entry):
    return (
        _next_equity_refresh_seconds()
        if entry.asset_class == "EQUITY"
        else ALPHA_VANTAGE_FX_POLL_SECONDS
    )


def stale_after_seconds(symbol):
    entry = runtime.active_entry(symbol)
    return (
        ALPHA_VANTAGE_EQUITY_STALE_SECONDS
        if entry is not None and entry.asset_class == "EQUITY"
        else ALPHA_VANTAGE_FX_STALE_SECONDS
    )


closed_stale_after_seconds = stale_after_seconds


def market_open(symbol):
    return None


reload_active = runtime.reload_active


def _classifier(symbol):
    return {
        "stale_after_seconds": stale_after_seconds(symbol),
        "closed_stale_after_seconds": closed_stale_after_seconds(symbol),
        "market_open": None,
    }


def _request_payload(entry):
    with _request_lock:
        if runtime.ledger.credits_today() >= ALPHA_VANTAGE_DAILY_BUDGET:
            raise ProviderDataError(
                ALPHA_VANTAGE,
                "daily request budget is spent for now",
            )
        if not runtime.try_take():
            wait = runtime.budget_wait_seconds() or 1
            raise ProviderDataError(
                ALPHA_VANTAGE,
                f"provider-wide request spacing is active: retry in {wait}s",
            )
        runtime.record_request()
        return _client.quote(entry.symbol, entry.asset_class)


def _fetch_and_publish(entry):
    payload = _request_payload(entry)
    with quote_lifecycle.locked_keys(entry.symbol, (ALPHA_VANTAGE,)):
        current = load_active_set().get(entry.symbol)
        if current is None or not current.serves(ALPHA_VANTAGE):
            raise ProviderDataError(
                ALPHA_VANTAGE,
                f"{entry.symbol} left the ALPHA_VANTAGE active set during refresh",
            )
        quote = normalize_quote(
            current.symbol,
            current.asset_class,
            current.currency,
            payload,
            utcnow(),
        )
        classifier = _classifier(current.symbol)
        changed, created, accepted = quote_store.store_quote(quote, classifier)
        if not accepted:
            raise ProviderDataError(
                ALPHA_VANTAGE,
                f"older observation for {current.symbol} ignored; current row retained",
            )
        if changed:
            audit_quote_write(ALPHA_VANTAGE, quote, created)
        tick = wire_tick(quote, classifier, current.origin(ALPHA_VANTAGE))
        publish_quote(tick)
    runtime.record_success()
    return tick


def _guarded_fetch(entry):
    return runtime.guarded(
        lambda: _fetch_and_publish(entry),
        "quote_unavailable",
        log_level="warning",
        symbol=entry.symbol,
    )


def _seed_new_entries(entries):
    current_symbols = {entry.symbol for entry in entries}
    _known_symbols.intersection_update(current_symbols)
    now = utcnow()
    latest_received_at = None
    for entry in entries:
        if entry.symbol in _known_symbols:
            continue
        provider_at, received_at = quote_store.quote_clocks(
            ALPHA_VANTAGE, entry.symbol
        )
        _known_symbols.add(entry.symbol)
        if provider_at is None or received_at is None:
            continue
        if (now - provider_at).total_seconds() > stale_after_seconds(entry.symbol):
            continue
        if latest_received_at is None or received_at > latest_received_at:
            latest_received_at = received_at
        if entry.asset_class == "EQUITY":
            _schedule.defer(entry.symbol, _next_equity_refresh_seconds())
        else:
            age = max(0, (now - received_at).total_seconds())
            _schedule.defer(
                entry.symbol,
                max(60, ALPHA_VANTAGE_FX_POLL_SECONDS - age),
            )
    if latest_received_at is not None:
        runtime.restore_success(latest_received_at.isoformat())


def poll_loop():
    if not ALPHA_VANTAGE_API_KEY:
        log.warning("alpha_vantage_disabled", reason="ALPHA_VANTAGE_API_KEY is not set")
        return
    while True:
        if runtime.cooldown_seconds_left() > 0:
            time.sleep(min(runtime.cooldown_seconds_left(), 5))
            continue
        if not runtime.reload_active_if_stale():
            time.sleep(5)
            continue
        pollable = runtime.pollable_entries()
        _seed_new_entries(pollable)
        for entry in _schedule.due_entries(pollable):
            tick, error = _guarded_fetch(entry)
            if tick is None:
                if "spacing" in str(error) or "budget" in str(error):
                    break
                _schedule.defer(entry.symbol, 300)
                continue
            _schedule.defer(entry.symbol, _cadence_seconds(entry))
        _schedule.keep_only(pollable)
        time.sleep(1)


def refresh_symbol(symbol):
    if not ALPHA_VANTAGE_API_KEY:
        return None, "ALPHA_VANTAGE is disabled: no API key configured", 503
    entry, error, status = runtime.resolve(symbol)
    if error is not None:
        return None, error, status
    unavailable = runtime.unavailable()
    if unavailable is not None:
        return None, unavailable, 503
    tick, error = _guarded_fetch(entry)
    if tick is None:
        daily = "daily request budget" in str(error)
        spacing = "request spacing" in str(error)
        status = 429 if daily or spacing or runtime.status() == "RATE_LIMITED" else 502
        return None, error, status
    _schedule.defer(symbol, _cadence_seconds(entry))
    return tick, None, 200


def search(query):
    return None


def active_symbols():
    return sorted(entry.symbol for entry in runtime.pollable_entries())


def poll_strategy():
    entries = runtime.pollable_entries()
    equities = sum(entry.asset_class == "EQUITY" for entry in entries)
    fx = sum(entry.asset_class == "FX" for entry in entries)
    next_due = _schedule.next_due_seconds(entries)
    return {
        "mode": "PERSISTED_DAILY_LEDGER",
        "daily_budget": ALPHA_VANTAGE_DAILY_BUDGET,
        "equity_grade": "EOD",
        "fx_poll_seconds": ALPHA_VANTAGE_FX_POLL_SECONDS,
        "next_batch_seconds": next_due,
        "symbol_count": len(entries),
        "description": (
            f"US equities once after session · FX at most twice daily · "
            f"{equities} EOD / {fx} FX on a persisted "
            f"{ALPHA_VANTAGE_DAILY_BUDGET}-call ledger"
        ),
    }


def runtime_snapshot():
    symbols = active_symbols()
    return {
        **runtime.snapshot(symbols),
        "market_states": {"open": 0, "closed": 0, "unknown": len(symbols)},
        "strategy": poll_strategy(),
    }
