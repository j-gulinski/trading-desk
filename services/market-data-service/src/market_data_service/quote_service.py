import threading

from market_data_service import official_fixing_set, quote_store, scheduler, watchlist
from market_data_service.config import SERVICE_NAME
from desk_domain.active_set import load_active_set
from desk_domain.freshness import classify
from desk_runtime.functions import utcnow
from desk_runtime.logging_config import get_logger

log = get_logger(SERVICE_NAME)


def board_rows(provider=None, symbol=None):
    active = load_active_set()
    official_fixings = official_fixing_set.official_fixing_board_symbols()
    rows = []
    for row in quote_store.board_rows(provider, symbol):
        row_provider, row_symbol = row["provider"], row["symbol"]
        if row_provider in official_fixings:
            if row_symbol not in official_fixings[row_provider]:
                continue
            origin = {
                "watched": False,
                "held": False,
                "benchmark": False,
                "reference": True,
            }
        else:
            entry = active.get(row_symbol)
            if entry is None or not entry.serves(row_provider):
                continue
            origin = {**entry.origin(row_provider), "reference": False}
        row["event_time"] = row["received_at"]
        row.update(origin)
        rows.append(row)
    return rows


def quote_rows(provider=None, symbol=None):
    now = utcnow()
    rows = board_rows(provider, symbol)
    for row in rows:
        row["freshness"] = classify(
            True,
            row["provider_timestamp"],
            row["received_at"],
            now,
            row["stale_after_seconds"],
            market_open=row["market_open"],
            closed_stale_after_seconds=row["closed_stale_after_seconds"],
        )
    return rows


def list_quotes(symbol=None, asset_class=None, provider=None):
    return [
        row for row in quote_rows(provider, symbol)
        if asset_class is None or row["asset_class"] == asset_class
    ]


def get_quote(provider, symbol):
    if provider not in scheduler.wired_providers():
        return None, f"unknown or unwired provider: {provider}", 404
    row = next(iter(quote_rows(provider, symbol)), None)
    if row is None:
        return None, f"no active quote for {provider}:{symbol}", 404
    return row, None, 200


def get_quote_history(provider, symbol, limit, include_raw=False):
    if provider not in scheduler.wired_providers():
        return None, f"unknown or unwired provider: {provider}", 404
    return quote_store.quote_history(provider, symbol, limit, include_raw), None, 200


def list_watchlist():
    return watchlist.list_items(scheduler.wired_quote_providers())


def _refresh_added_feeds(symbol, providers):
    for provider in providers:
        _, error, _ = scheduler.refresh_symbol(symbol, provider)
        log.info(
            "watchlist_add_refresh",
            symbol=symbol,
            provider=provider,
            outcome="ok" if error is None else error,
        )


def add_watchlist_item(body):
    item, error, status = watchlist.add_item(
        body.get("symbol"),
        body.get("asset_class"),
        body.get("currency"),
        scheduler.wired_quote_providers(),
        body.get("providers"),
        body.get("name"),
        body.get("market"),
    )
    if error is not None:
        return None, error, status
    scheduler.reload_active_set()
    threading.Thread(
        target=_refresh_added_feeds,
        args=(item["symbol"], item["added_providers"]),
        daemon=True,
    ).start()
    log.info(
        "watchlist_symbol_added",
        symbol=item["symbol"],
        asset_class=item["asset_class"],
        providers=[provider for provider, enabled in item["providers"].items() if enabled],
    )
    return item, None, status


def remove_watchlist_item(symbol, provider=None):
    result, error, status = watchlist.remove_item(symbol, provider)
    if error is not None:
        return None, error, status
    scheduler.reload_active_set()
    normalized = symbol.strip().upper()
    active = load_active_set().get(normalized)
    released = [
        name for name in result["dropped"]
        if active is None or not active.serves(name)
    ]
    log.info(
        "watchlist_symbol_removed",
        symbol=normalized,
        provider=provider,
        released=released,
        remaining=result["remaining"],
    )
    return {
        "symbol": normalized,
        "removed_providers": result["dropped"],
        "remaining_providers": result["remaining"],
        "still_polled": [name for name in result["dropped"] if name not in released],
    }, None, status


def refresh(symbol=None, provider=None):
    if symbol is None:
        refreshed, skipped = scheduler.refresh_all(provider)
        log.info(
            "manual_refresh_all",
            provider=provider,
            refreshed=len(refreshed),
            skipped=skipped,
        )
        return {"refreshed": refreshed, "skipped": skipped}, None, 200
    tick, error, status = scheduler.refresh_symbol(symbol, provider)
    if error is not None:
        log.warning(
            "manual_refresh_rejected",
            symbol=symbol,
            provider=provider,
            reason=error,
        )
        return None, error, status
    log.info("manual_refresh", symbol=symbol, provider=provider)
    return tick, None, status
