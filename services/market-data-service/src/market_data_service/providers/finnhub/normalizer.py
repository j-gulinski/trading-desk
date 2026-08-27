"""Translate Finnhub response fields into the desk's quote and instrument contracts."""

from datetime import datetime, timezone

from market_data_service.providers.base import ProviderDataError
from desk_domain.providers import FINNHUB, quote_grade
from desk_domain.quotes import as_decimal, build_quote
from desk_domain.symbols import is_valid_symbol


def _day_value(payload, key):
    value = payload.get(key)
    if value in (None, ""):
        return None
    number = as_decimal(value)
    return None if number == 0 else number


def normalize_quote(symbol, asset_class, currency, payload, received_at):
    last = payload.get("c") if isinstance(payload, dict) else None
    traded_at = payload.get("t") if isinstance(payload, dict) else None
    if not last or not traded_at:
        raise ProviderDataError(FINNHUB, f"no quote data for {symbol}")
    return build_quote(
        provider=FINNHUB,
        symbol=symbol,
        asset_class=asset_class,
        quote_grade=quote_grade(FINNHUB, asset_class),
        received_at=received_at,
        raw_payload=payload,
        currency=currency,
        last=last,
        previous_close=_day_value(payload, "pc"),
        provider_timestamp=datetime.fromtimestamp(traded_at, tz=timezone.utc),
    )


def normalize_search_results(payload):
    results = []
    for item in (payload.get("result") or []) if isinstance(payload, dict) else []:
        symbol = (item.get("symbol") or "").upper()
        if not is_valid_symbol(symbol):
            continue
        results.append({
            "provider": FINNHUB,
            "symbol": symbol,
            "provider_symbol": symbol,
            "name": item.get("description") or symbol,
            "asset_class": "EQUITY",
            "currency": "USD",
            "exchange": "US",
        })
    return results
