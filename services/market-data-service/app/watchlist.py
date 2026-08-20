import re

from shared.audit import write_audit
from shared.db import session_scope
from shared.functions import utcnow
from shared.models import WatchlistItem
from shared.providers import supports_quotes
from shared.symbols import (
    SPOT_ASSET_CLASSES,
    is_valid_symbol,
    watched_providers,
    watchlist_items,
)
from app.config import MAX_ACTIVE_SYMBOLS, SERVICE_NAME

CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


def _describe(symbol, asset_class, currency, chosen, quote_providers):
    return {
        "symbol": symbol,
        "asset_class": asset_class,
        "currency": currency,
        "providers": {provider: provider in chosen for provider in quote_providers},
        "capabilities": {
            provider: supports_quotes(provider, asset_class)
            for provider in quote_providers
        },
    }


def list_items(quote_providers):
    with session_scope() as session:
        rows = [
            (item.symbol, item.asset_class, item.currency,
             watched_providers(item.asset_class, item.providers), item.created_at)
            for item in watchlist_items(session)
        ]
    return [
        {**_describe(symbol, asset_class, currency, chosen, quote_providers),
         "created_at": created_at}
        for symbol, asset_class, currency, chosen, created_at in rows
    ]


def _requested_providers(requested, asset_class, quote_providers):
    capable = [p for p in quote_providers if supports_quotes(p, asset_class)]
    if requested is None:
        return set(capable), None
    if not isinstance(requested, list) or not requested:
        return None, "providers must be a non-empty list"
    chosen = {str(provider).strip().upper() for provider in requested}
    unknown = chosen - set(quote_providers)
    if unknown:
        return None, f"unknown provider: {', '.join(sorted(unknown))}"
    incapable = chosen - set(capable)
    if incapable:
        return None, f"{', '.join(sorted(incapable))} cannot quote {asset_class}"
    return chosen, None


def add_item(symbol, asset_class, currency, quote_providers, requested_providers=None):
    symbol = (symbol or "").strip().upper()
    asset_class = (asset_class or "").strip().upper()
    currency = (currency or "").strip().upper()
    if not is_valid_symbol(symbol):
        return None, "symbol must be 2-32 characters: A-Z 0-9 . _ -", 400
    if asset_class not in SPOT_ASSET_CLASSES:
        return None, f"asset_class must be one of {', '.join(SPOT_ASSET_CLASSES)}", 400
    if not CURRENCY_PATTERN.match(currency):
        return None, "currency must be a 3-letter ISO code", 400
    chosen, error = _requested_providers(requested_providers, asset_class, quote_providers)
    if error is not None:
        return None, error, 400
    if not chosen:
        return None, f"no wired provider can quote {asset_class}", 422

    with session_scope() as session:
        row = session.get(WatchlistItem, symbol)
        if row is not None:
            if row.asset_class != asset_class:
                return None, f"{symbol} is already watched as {row.asset_class}", 409
            if row.currency != currency:
                return None, (
                    f"{symbol} is already watched in {row.currency}, not {currency}"
                ), 409
            current = watched_providers(row.asset_class, row.providers)
            added = chosen - current
            if not added:
                return None, f"{symbol} is already watched on {', '.join(sorted(chosen))}", 409
            merged = current | added
            row.providers = {provider: True for provider in sorted(merged)}
            event, message = "WATCHLIST_PROVIDER_ADDED", (
                f"{symbol} watched on {', '.join(sorted(added))}"
            )
        else:
            if session.query(WatchlistItem).count() >= MAX_ACTIVE_SYMBOLS:
                return None, (
                    f"the watchlist is full ({MAX_ACTIVE_SYMBOLS} symbols) — "
                    "remove one before adding another"
                ), 409
            merged = chosen
            session.add(WatchlistItem(
                symbol=symbol,
                asset_class=asset_class,
                currency=currency,
                providers={provider: True for provider in sorted(merged)},
                created_at=utcnow(),
            ))
            event, message = "WATCHLIST_SYMBOL_ADDED", (
                f"{symbol} ({asset_class}, {currency}) watched on "
                f"{', '.join(sorted(merged))}"
            )
        write_audit(
            SERVICE_NAME, event, message,
            entity_type="SYMBOL", entity_id=symbol,
            payload={"asset_class": asset_class, "currency": currency,
                     "providers": sorted(merged)},
            session=session,
        )
    return _describe(symbol, asset_class, currency, merged, quote_providers), None, 201


def remove_item(symbol, provider=None):
    symbol = (symbol or "").strip().upper()
    provider = (provider or "").strip().upper() or None
    with session_scope() as session:
        row = session.get(WatchlistItem, symbol)
        if row is None:
            return None, f"{symbol} is not on the watchlist", 404
        current = watched_providers(row.asset_class, row.providers)
        if provider is not None and provider not in current:
            return None, f"{symbol} is not watched on {provider}", 404
        remaining = current - {provider} if provider is not None else set()
        if remaining:
            row.providers = {name: True for name in sorted(remaining)}
            event = "WATCHLIST_PROVIDER_REMOVED"
            message = f"{symbol} no longer watched on {provider}"
        else:
            session.delete(row)
            event = "WATCHLIST_SYMBOL_REMOVED"
            message = (
                f"{symbol} removed from the watchlist"
                if provider is None
                else f"{symbol} removed from the watchlist with its last provider {provider}"
            )
        write_audit(
            SERVICE_NAME, event, message,
            entity_type="SYMBOL", entity_id=symbol,
            payload={"provider": provider, "remaining_providers": sorted(remaining)},
            session=session,
        )
        dropped = sorted(current - remaining)
    return {"remaining": sorted(remaining), "dropped": dropped}, None, 200
