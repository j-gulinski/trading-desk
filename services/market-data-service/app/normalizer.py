from datetime import datetime, timezone

from app.clients.base import ProviderDataError
from shared.providers import FINNHUB, TWELVE_DATA, quote_grade
from shared.quotes import as_decimal, build_quote


def _day_value(payload, key):
    value = payload.get(key)
    if value is None or value == "":
        return None
    number = as_decimal(value)
    return None if number == 0 else number


def normalize_finnhub_quote(symbol, asset_class, currency, payload, received_at):
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


def normalize_twelve_data_quote(symbol, asset_class, currency, payload, received_at):
    if not isinstance(payload, dict) or payload.get("status") == "error":
        detail = payload.get("message") if isinstance(payload, dict) else None
        raise ProviderDataError(TWELVE_DATA, str(detail or f"no quote data for {symbol}"))
    last = payload.get("close")
    quoted_at = payload.get("last_quote_at") or payload.get("timestamp")
    if not last or not quoted_at:
        raise ProviderDataError(TWELVE_DATA, f"no quote data for {symbol}")
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
