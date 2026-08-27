"""Translate NBP daily table and gold fixing responses into reference quotes."""

from datetime import datetime, timezone

from market_data_service.providers.base import ProviderDataError
from desk_domain.providers import NBP, quote_grade
from desk_domain.quotes import build_quote


def _as_of_timestamp(date_text):
    return datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def normalize_rate(symbol, table_payload, received_at):
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
        provider_timestamp=_as_of_timestamp(table_payload["effectiveDate"]),
    )


def normalize_gold(symbol, payload, received_at):
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
        provider_timestamp=_as_of_timestamp(payload["data"]),
    )
