import re
import threading

from sqlalchemy.exc import IntegrityError

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
MAX_NAME_LENGTH = 160
MAX_MARKET_LENGTH = 40
COUNTRY_MARKETS = {"US", "USA", "UNITED STATES"}
_mutation_lock = threading.Lock()


def _describe(symbol, name, asset_class, currency, market, chosen, quote_providers):
    return {
        "symbol": symbol,
        "name": name,
        "asset_class": asset_class,
        "currency": currency,
        "market": market,
        "providers": {provider: provider in chosen for provider in quote_providers},
        "capabilities": {
            provider: supports_quotes(provider, asset_class)
            for provider in quote_providers
        },
    }


def list_items(quote_providers):
    with session_scope() as session:
        rows = [
            (item.symbol, item.name, item.asset_class, item.currency, item.market,
             watched_providers(item.asset_class, item.providers), item.created_at)
            for item in watchlist_items(session)
        ]
    return [
        {**_describe(symbol, name, asset_class, currency, market, chosen, quote_providers),
         "created_at": created_at}
        for symbol, name, asset_class, currency, market, chosen, created_at in rows
    ]


def matching_identities(query):
    normalized = str(query or "").replace("/", "").upper()
    with session_scope() as session:
        rows = [
            (item.symbol, item.name, item.asset_class, item.currency, item.market)
            for item in watchlist_items(session)
            if normalized in item.symbol.replace("/", "").upper()
            or normalized in str(item.name or "").upper()
        ]
    return [
        {
            "symbol": symbol,
            "name": name or symbol,
            "asset_class": asset_class,
            "currency": currency,
            "exchange": market,
        }
        for symbol, name, asset_class, currency, market in rows
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


def _optional_identity(value, field, max_length):
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, f"{field} must be text"
    normalized = value.strip()
    if not normalized:
        return None, None
    if len(normalized) > max_length:
        return None, f"{field} must be at most {max_length} characters"
    return normalized, None


def _add_item(symbol, asset_class, currency, quote_providers, requested_providers=None,
              name=None, market=None):
    if not all(isinstance(value, str) for value in (symbol, asset_class, currency)):
        return None, "symbol, asset_class and currency must be text", 400
    symbol = symbol.strip().upper()
    asset_class = asset_class.strip().upper()
    currency = currency.strip().upper()
    if not is_valid_symbol(symbol):
        return None, "symbol must be 2-32 characters: A-Z 0-9 . _ : -", 400
    if asset_class not in SPOT_ASSET_CLASSES:
        return None, f"asset_class must be one of {', '.join(SPOT_ASSET_CLASSES)}", 400
    if not CURRENCY_PATTERN.match(currency):
        return None, "currency must be a 3-letter ISO code", 400
    name, error = _optional_identity(name, "name", MAX_NAME_LENGTH)
    if error is not None:
        return None, error, 400
    market, error = _optional_identity(market, "market", MAX_MARKET_LENGTH)
    if error is not None:
        return None, error, 400
    market = market.upper() if market else None
    if market in COUNTRY_MARKETS:
        market = None
    if asset_class in ("FX", "COMMODITY"):
        market = "OTC"
    elif market is None and ":" in symbol:
        market = symbol.rpartition(":")[2]
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
            if name is not None:
                row.name = name
            if market is not None:
                row.market = market
            name = row.name
            market = row.market
            event, message = "WATCHLIST_PROVIDER_ADDED", (
                f"{symbol} watched on {', '.join(sorted(added))}"
            )
        else:
            added = chosen
            if session.query(WatchlistItem).count() >= MAX_ACTIVE_SYMBOLS:
                return None, (
                    f"the watchlist is full ({MAX_ACTIVE_SYMBOLS} symbols) — "
                    "remove one before adding another"
                ), 409
            merged = chosen
            session.add(WatchlistItem(
                symbol=symbol,
                name=name,
                asset_class=asset_class,
                currency=currency,
                market=market,
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
                     "name": name, "market": market,
                     "providers": sorted(merged)},
            session=session,
        )
    item = _describe(symbol, name, asset_class, currency, market, merged, quote_providers)
    item["added_providers"] = sorted(added)
    return item, None, 201


def add_item(symbol, asset_class, currency, quote_providers, requested_providers=None,
             name=None, market=None):
    with _mutation_lock:
        try:
            return _add_item(
                symbol,
                asset_class,
                currency,
                quote_providers,
                requested_providers,
                name,
                market,
            )
        except IntegrityError:
            return None, "the watchlist changed concurrently; retry the request", 409


def _remove_item(symbol, provider=None):
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


def remove_item(symbol, provider=None):
    with _mutation_lock:
        try:
            return _remove_item(symbol, provider)
        except IntegrityError:
            return None, "the watchlist changed concurrently; retry the request", 409
