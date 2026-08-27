"""Translate ECB EXR csvdata rows into the desk's reference-quote contract."""

from datetime import datetime, timezone

from market_data_service.providers.base import ProviderDataError
from desk_domain.providers import ECB, quote_grade
from desk_domain.quotes import build_quote


def _as_of_timestamp(date_text):
    return datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def normalize_rate(symbol, payload, received_at):
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
        provider_timestamp=_as_of_timestamp(row["TIME_PERIOD"]),
    )
