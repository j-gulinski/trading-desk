import threading

from market_data_service import feeds, quote_board, quote_store, watchlist
from market_data_service.config import SERVICE_NAME
from desk_runtime.logging_config import get_logger

log = get_logger(SERVICE_NAME)


def get_quote_history(provider, symbol, limit, include_raw=False):
    if provider not in feeds.WIRED_PROVIDERS:
        return None, f"unknown or unwired provider: {provider}", 404
    return quote_store.quote_history(provider, symbol, limit, include_raw), None, 200


def list_watchlist():
    return watchlist.list_items(feeds.WATCHLIST_PROVIDERS)


def _refresh_added_feeds(symbol, providers):
    for provider in providers:
        _, error, _ = feeds.refresh_symbol(symbol, provider)
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
        feeds.WATCHLIST_PROVIDERS,
        body.get("providers"),
        body.get("name"),
        body.get("market"),
    )
    if error is not None:
        return None, error, status
    quote_board.reload()
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
    quote_board.reload()
    normalized = symbol.strip().upper()
    entry = quote_board.active_entry(normalized)
    released = [
        name for name in result["dropped"]
        if entry is None or not entry.serves(name)
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
        refreshed, skipped = feeds.refresh_all(provider)
        log.info(
            "manual_refresh_all",
            provider=provider,
            refreshed=len(refreshed),
            skipped=skipped,
        )
        return {"refreshed": refreshed, "skipped": skipped}, None, 200
    tick, error, status = feeds.refresh_symbol(symbol, provider)
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
