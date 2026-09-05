from datetime import datetime, timezone

from market_data_service.providers.base import ProviderDataError
from desk_domain.providers import TWELVE_DATA, quote_grade
from desk_domain.quotes import as_decimal, build_quote
from desk_domain.symbols import is_valid_symbol

METAL_BASES = ("XAU", "XAG", "XPT", "XPD")
US_EQUITY_EXCHANGES = {
    "AMEX", "BATS", "CBOE", "IEX", "NASDAQ", "NYSE", "OTC", "US",
}


def _day_value(payload, key):
    value = payload.get(key)
    if value in (None, ""):
        return None
    number = as_decimal(value)
    return None if number == 0 else number


def normalize_quote(symbol, asset_class, currency, payload, received_at):
    if not isinstance(payload, dict) or payload.get("status") == "error":
        detail = payload.get("message") if isinstance(payload, dict) else None
        raise ProviderDataError(TWELVE_DATA, str(detail or f"no quote data for {symbol}"))
    last = payload.get("close")
    quoted_at = payload.get("last_quote_at") or payload.get("timestamp")
    if not last or not quoted_at:
        raise ProviderDataError(TWELVE_DATA, f"no quote data for {symbol}")
    payload_currency = str(payload.get("currency") or "").strip().upper()
    expected_currency = str(currency or "").strip().upper()
    if payload_currency and expected_currency and payload_currency != expected_currency:
        raise ProviderDataError(
            TWELVE_DATA,
            f"quote identity mismatch for {symbol}: expected {expected_currency}, "
            f"provider returned {payload_currency}",
        )
    _, separator, expected_exchange = symbol.rpartition(":")
    payload_exchange = str(payload.get("exchange") or "").strip().upper()
    if separator and payload_exchange and payload_exchange != expected_exchange:
        raise ProviderDataError(
            TWELVE_DATA,
            f"quote identity mismatch for {symbol}: expected {expected_exchange}, "
            f"provider returned {payload_exchange}",
        )
    return build_quote(
        provider=TWELVE_DATA,
        symbol=symbol,
        asset_class=asset_class,
        quote_grade=quote_grade(TWELVE_DATA, asset_class),
        received_at=received_at,
        raw_payload=payload,
        currency=currency,
        last=last,
        previous_close=_day_value(payload, "previous_close"),
        provider_timestamp=datetime.fromtimestamp(int(quoted_at), tz=timezone.utc),
    )


def normalize_search_results(payload):
    results = []
    for item in (payload.get("data") or []) if isinstance(payload, dict) else []:
        raw = (item.get("symbol") or "").upper()
        if "/" in raw:
            base, _, quote = raw.partition("/")
            symbol = f"{base}{quote}"
            provider_symbol = raw
            asset_class = "COMMODITY" if base in METAL_BASES else "FX"
            currency = quote
        else:
            exchange = (item.get("exchange") or "").strip().upper()
            country = (item.get("country") or "").strip().upper()
            us_equity = country in ("US", "UNITED STATES") or exchange in US_EQUITY_EXCHANGES
            symbol = raw if us_equity or not exchange else f"{raw}:{exchange}"
            provider_symbol = symbol
            asset_class = "EQUITY"
            currency = (item.get("currency") or "USD").upper()
        if not is_valid_symbol(symbol):
            continue
        results.append({
            "provider": TWELVE_DATA,
            "symbol": symbol,
            "provider_symbol": provider_symbol,
            "name": item.get("instrument_name") or symbol,
            "asset_class": asset_class,
            "currency": currency,
            "exchange": item.get("exchange") or None,
        })
    return results
