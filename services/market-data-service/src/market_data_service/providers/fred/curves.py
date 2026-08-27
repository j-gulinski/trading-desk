"""Build the FRED-backed USD government curve."""

from datetime import datetime
from decimal import Decimal

from market_data_service.providers.base import ProviderDataError
from desk_domain.curves import (
    GOVERNMENT_BONDS,
    USD_GOVERNMENT_BONDS,
    build_curve_point,
    build_curve_set,
    curve_currency,
)
from desk_runtime.functions import utcnow
from desk_domain.providers import FRED
from desk_domain.quotes import as_decimal

DGS_SERIES = (
    ("1M", Decimal("0.083333"), "DGS1MO"),
    ("3M", Decimal("0.25"), "DGS3MO"),
    ("6M", Decimal("0.5"), "DGS6MO"),
    ("1Y", Decimal(1), "DGS1"),
    ("2Y", Decimal(2), "DGS2"),
    ("3Y", Decimal(3), "DGS3"),
    ("5Y", Decimal(5), "DGS5"),
    ("7Y", Decimal(7), "DGS7"),
    ("10Y", Decimal(10), "DGS10"),
    ("20Y", Decimal(20), "DGS20"),
    ("30Y", Decimal(30), "DGS30"),
)
FRED_DAILY_LOOKBACK = 7
MIN_USD_CURVE_POINTS = 8


def _as_of(date_text):
    return datetime.strptime(date_text, "%Y-%m-%d").date()


def _latest(client, record_request, series_id, lookback):
    record_request()
    payload = client.latest_observations(series_id, lookback)
    observations = payload.get("observations") if isinstance(payload, dict) else None
    if not observations:
        raise ProviderDataError(FRED, f"{series_id} returned no observations")
    for observation in observations:
        value = observation.get("value")
        if value not in (None, "", "."):
            return _as_of(observation["date"]), as_decimal(value), payload
    raise ProviderDataError(FRED, f"{series_id} carries only missing values")


def build_usd_government_curve(client, record_request):
    points = []
    raw = {}
    for label, years, series_id in DGS_SERIES:
        try:
            as_of, rate, payload = _latest(
                client, record_request, series_id, FRED_DAILY_LOOKBACK
            )
        except ProviderDataError:
            raw[series_id] = {"error": "no usable observation"}
            continue
        raw[series_id] = payload
        points.append(build_curve_point(label, years, rate, series_id, as_of))
    if (
        len(points) < MIN_USD_CURVE_POINTS
        or min(point.tenor_years for point in points) > Decimal(1)
        or max(point.tenor_years for point in points) < Decimal(10)
    ):
        raise ProviderDataError(
            FRED,
            f"incomplete Treasury curve: {len(points)}/{len(DGS_SERIES)} usable tenors",
        )
    return build_curve_set(
        provider=FRED,
        curve_name=USD_GOVERNMENT_BONDS,
        curve_basis=GOVERNMENT_BONDS,
        currency=curve_currency(USD_GOVERNMENT_BONDS),
        as_of_date=min(point.source_as_of for point in points),
        received_at=utcnow(),
        points=points,
        raw_payload=raw,
    )
