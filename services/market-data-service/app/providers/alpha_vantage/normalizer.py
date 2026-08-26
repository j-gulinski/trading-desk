from datetime import datetime, time, timezone

from app.providers.base import ProviderDataError
from shared.providers import ALPHA_VANTAGE, quote_grade
from shared.quotes import build_quote


def _equity_quote(symbol, currency, payload, received_at):
    if currency != "USD" or ":" in symbol:
        raise ProviderDataError(
            ALPHA_VANTAGE,
            f"equity identity mismatch for {symbol}: expected an unqualified US/USD symbol",
        )
    quote = payload.get("Global Quote") if isinstance(payload, dict) else None
    if not isinstance(quote, dict) or not quote:
        raise ProviderDataError(ALPHA_VANTAGE, f"no EOD quote data for {symbol}")
    returned = str(quote.get("01. symbol") or "").strip().upper()
    if returned != symbol:
        raise ProviderDataError(
            ALPHA_VANTAGE,
            f"quote identity mismatch for {symbol}: provider returned {returned or 'no symbol'}",
        )
    try:
        as_of = datetime.strptime(
            str(quote.get("07. latest trading day") or ""), "%Y-%m-%d"
        ).date()
    except ValueError as error:
        raise ProviderDataError(ALPHA_VANTAGE, f"no EOD date for {symbol}") from error
    return build_quote(
        provider=ALPHA_VANTAGE,
        symbol=symbol,
        asset_class="EQUITY",
        quote_grade=quote_grade(ALPHA_VANTAGE, "EQUITY"),
        received_at=received_at,
        raw_payload=quote,
        currency=currency,
        last=quote.get("05. price"),
        previous_close=quote.get("08. previous close"),
        provider_timestamp=datetime.combine(as_of, time.min, tzinfo=timezone.utc),
    )


def _fx_quote(symbol, currency, payload, received_at):
    quote = payload.get("Realtime Currency Exchange Rate") \
        if isinstance(payload, dict) else None
    if not isinstance(quote, dict) or not quote:
        raise ProviderDataError(ALPHA_VANTAGE, f"no FX quote data for {symbol}")
    returned_base = str(quote.get("1. From_Currency Code") or "").strip().upper()
    returned_quote = str(quote.get("3. To_Currency Code") or "").strip().upper()
    if returned_base + returned_quote != symbol or returned_quote != currency:
        raise ProviderDataError(
            ALPHA_VANTAGE,
            f"quote identity mismatch for {symbol}: provider returned "
            f"{returned_base or '?'}{returned_quote or '?'}",
        )
    zone = str(quote.get("7. Time Zone") or "UTC").strip().upper()
    if zone not in ("UTC", "GMT"):
        raise ProviderDataError(
            ALPHA_VANTAGE,
            f"unsupported provider timestamp zone {zone}",
        )
    try:
        quoted_at = datetime.strptime(
            str(quote.get("6. Last Refreshed") or ""), "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise ProviderDataError(ALPHA_VANTAGE, f"no FX timestamp for {symbol}") from error
    return build_quote(
        provider=ALPHA_VANTAGE,
        symbol=symbol,
        asset_class="FX",
        quote_grade=quote_grade(ALPHA_VANTAGE, "FX"),
        received_at=received_at,
        raw_payload=quote,
        currency=currency,
        bid=quote.get("8. Bid Price"),
        ask=quote.get("9. Ask Price"),
        last=quote.get("5. Exchange Rate"),
        provider_timestamp=quoted_at,
    )


def normalize_quote(symbol, asset_class, currency, payload, received_at):
    if asset_class == "EQUITY":
        return _equity_quote(symbol, currency, payload, received_at)
    if asset_class == "FX":
        return _fx_quote(symbol, currency, payload, received_at)
    raise ProviderDataError(
        ALPHA_VANTAGE,
        f"{asset_class} is not supported by this adapter",
    )


def attach_search_result(result):
    asset_class = result.get("asset_class")
    symbol = str(result.get("symbol") or "").upper()
    currency = str(result.get("currency") or "").upper()
    if asset_class == "EQUITY":
        if ":" in symbol or currency != "USD":
            return None
        exchange = "US"
    elif asset_class == "FX" and len(symbol) == 6 and currency == symbol[3:]:
        exchange = "OTC"
    else:
        return None
    return {
        "provider": ALPHA_VANTAGE,
        "symbol": symbol,
        "provider_symbol": symbol if asset_class == "EQUITY" else f"{symbol[:3]}/{symbol[3:]}",
        "name": result.get("name") or symbol,
        "asset_class": asset_class,
        "currency": currency,
        "exchange": exchange,
    }
