"""Which provider:symbol rows are served; the one path that stores, publishes and removes them."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
import threading
import time

from desk_domain.active_set import load_active_set
from desk_domain.quotes import quote_state, wire_tick
from desk_runtime.functions import utcnow
from desk_runtime.logging_config import get_logger
from market_data_service import official_fixing_set, quote_store
from market_data_service.config import (
    ACTIVE_SET_REFRESH_SECONDS,
    RETENTION_SWEEP_INTERVAL_SECONDS,
    SERVICE_NAME,
    SNAPSHOT_RETENTION_DAYS,
)
from market_data_service.providers.base import ProviderDataError
from market_data_service.publisher import publish_quote, publish_removal

log = get_logger(SERVICE_NAME)


@dataclass(frozen=True)
class ServedSet:
    """Active symbols (watchlist, open trades, benchmark) and official fixings."""

    active: dict
    fixings: dict

    def serves(self, provider, symbol):
        if provider in self.fixings:
            return symbol in self.fixings[provider]
        entry = self.active.get(symbol)
        return entry is not None and entry.serves(provider)

    def origin(self, provider, symbol):
        if provider in self.fixings:
            return {"watched": False, "held": False, "benchmark": False, "reference": True}
        return {**self.active[symbol].origin(provider), "reference": False}

    def keys(self):
        keys = {(provider, symbol) for provider, symbols in self.fixings.items() for symbol in symbols}
        keys.update(
            (provider, entry.symbol)
            for entry in self.active.values()
            for provider in entry.providers
            if entry.serves(provider)
        )
        return keys


_served = ServedSet({}, {})
_loaded_at = None
_reload_lock = threading.Lock()
_key_locks = {}
_key_locks_lock = threading.Lock()


@contextmanager
def _locked(provider, symbol):
    with _key_locks_lock:
        lock = _key_locks.setdefault((provider, symbol), threading.Lock())
    with lock:
        yield


def reload():
    """Reads the served set from the database and removes rows that are no longer served."""
    global _served, _loaded_at
    with _reload_lock:
        fresh = ServedSet(load_active_set(), official_fixing_set.official_fixing_board_symbols())
        dropped = _served.keys() - fresh.keys()
        _served, _loaded_at = fresh, time.monotonic()
        _remove(dropped)


def reload_if_stale():
    if _loaded_at is None or time.monotonic() - _loaded_at >= ACTIVE_SET_REFRESH_SECONDS:
        reload()


def active_entry(symbol):
    return _served.active.get(symbol)


def entries_for(provider):
    return [entry for entry in _served.active.values() if entry.serves(provider)]


def fixing_symbols(provider):
    return _served.fixings.get(provider, frozenset())


def store_and_publish(quote, classifier):
    """Stores and publishes a served quote; raises ProviderDataError otherwise."""
    provider, symbol = quote.provider, quote.symbol
    with _locked(provider, symbol):
        served = _served
        if not served.serves(provider, symbol):
            raise ProviderDataError(provider, f"{symbol} is no longer served by {provider}")
        if not quote_store.store_quote(quote, classifier):
            raise ProviderDataError(
                provider, f"older observation for {symbol} ignored; current row retained",
            )
        origin = served.origin(provider, symbol)
        tick = wire_tick(quote, classifier, origin, reference=origin["reference"])
        publish_quote(tick)
    return tick


def board_rows():
    """Stored board rows that are still served, with why each one is on the board."""
    reload_if_stale()
    served = _served
    return [
        {**row, **quote_state(row), "event_time": row["received_at"],
         **served.origin(row["provider"], row["symbol"])}
        for row in quote_store.board_rows()
        if served.serves(row["provider"], row["symbol"])
    ]


def remove_strays():
    """Deletes stored board rows that nobody serves any more."""
    reload_if_stale()
    served = _served
    removed = _remove(
        (row["provider"], row["symbol"])
        for row in quote_store.board_rows()
        if not served.serves(row["provider"], row["symbol"])
    )
    if removed:
        log.info("board_strays_swept", rows=removed)


def _remove(keys):
    removed = 0
    for provider, symbol in sorted(keys):
        with _locked(provider, symbol):
            if _served.serves(provider, symbol) or not quote_store.delete_board_row(provider, symbol):
                continue
            publish_removal([{"provider": provider, "symbol": symbol}])
        removed += 1
    return removed


def _expire_snapshots():
    deleted = quote_store.delete_snapshots_before(utcnow() - timedelta(days=SNAPSHOT_RETENTION_DAYS))
    log.info("snapshot_retention_swept", deleted=deleted, retention_days=SNAPSHOT_RETENTION_DAYS)


def retention_loop():
    while True:
        for sweep in (_expire_snapshots, remove_strays):
            try:
                sweep()
            except Exception:
                log.exception("retention_sweep_failed", sweep=sweep.__name__)
        time.sleep(RETENTION_SWEEP_INTERVAL_SECONDS)
