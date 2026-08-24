from datetime import datetime, timezone

from app.clients.base import ProviderDataError
from shared.providers import ECB, FINNHUB, NBP, TWELVE_DATA, quote_grade
from shared.quotes import as_decimal, build_quote


def as_of_timestamp(date_text):
    return datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _day_value(payload, key):
    value = payload.get(key)
    if value is None or value == "":
        return None
    number = as_decimal(value)
    return None if number == 0 else number


def _session_count(payload, key):
    # a published zero volume is a real observation, unlike a zero price
    value = payload.get(key)
    return None if value in (None, "") else as_decimal(value)


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
        day_open=_day_value(payload, "o"),
        day_high=_day_value(payload, "h"),
        day_low=_day_value(payload, "l"),
        provider_timestamp=datetime.fromtimestamp(traded_at, tz=timezone.utc),
    )


def normalize_nbp_rate(symbol, table_payload, received_at):
    code = symbol[:3]
    rate = next(
        (item for item in table_payload.get("rates", []) if item.get("code") == code),
        None,
    )
    if rate is None or rate.get("mid") in (None, ""):
        raise ProviderDataError(NBP, f"table A carries no {code} rate")
    return build_quote(
        provider=NBP,
        symbol=symbol,
        asset_class="FX",
        quote_grade=quote_grade(NBP, "FX"),
        received_at=received_at,
        raw_payload=table_payload,
        currency="PLN",
        reference_mid=rate["mid"],
        provider_timestamp=as_of_timestamp(table_payload["effectiveDate"]),
    )


def normalize_nbp_gold(symbol, payload, received_at):
    if not isinstance(payload, dict) or payload.get("cena") in (None, ""):
        raise ProviderDataError(NBP, "no gold fixing in response")
    return build_quote(
        provider=NBP,
        symbol=symbol,
        asset_class="COMMODITY",
        quote_grade=quote_grade(NBP, "COMMODITY"),
        received_at=received_at,
        raw_payload=payload,
        currency="PLN",
        reference_mid=payload["cena"],
        provider_timestamp=as_of_timestamp(payload["data"]),
    )


def normalize_ecb_rate(symbol, payload, received_at):
    code = symbol[3:]
    row = next(
        (
            item for item in payload.get("rows", [])
            if item.get("CURRENCY") == code and item.get("OBS_VALUE")
        ),
        None,
    )
    if row is None:
        raise ProviderDataError(ECB, f"EXR response carries no EUR/{code} observation")
    return build_quote(
        provider=ECB,
        symbol=symbol,
        asset_class="FX",
        quote_grade=quote_grade(ECB, "FX"),
        received_at=received_at,
        raw_payload=payload,
        currency=code,
        reference_mid=row["OBS_VALUE"],
        provider_timestamp=as_of_timestamp(row["TIME_PERIOD"]),
    )


def normalize_twelve_data_quote(symbol, asset_class, currency, payload, received_at):
    if not isinstance(payload, dict) or payload.get("status") == "error":
        detail = payload.get("message") if isinstance(payload, dict) else None
        raise ProviderDataError(TWELVE_DATA, str(detail or f"no quote data for {symbol}"))
    last = payload.get("close")
    quoted_at = payload.get("last_quote_at") or payload.get("timestamp")
    if not last or not quoted_at:
        raise ProviderDataError(TWELVE_DATA, f"no quote data for {symbol}")
    week52 = payload.get("fifty_two_week") or {}
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
        day_open=_day_value(payload, "open"),
        day_high=_day_value(payload, "high"),
        day_low=_day_value(payload, "low"),
        week52_high=_day_value(week52, "high") if isinstance(week52, dict) else None,
        week52_low=_day_value(week52, "low") if isinstance(week52, dict) else None,
        volume=_session_count(payload, "volume"),
        average_volume=_session_count(payload, "average_volume"),
        provider_timestamp=datetime.fromtimestamp(int(quoted_at), tz=timezone.utc),
    )
