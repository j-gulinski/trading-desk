"""Build the two ECB euro-area government-bond curves from YC csvdata."""

from datetime import datetime
from decimal import Decimal

from market_data_service.providers.base import ProviderDataError
from desk_domain.curves import (
    EUR_GOVERNMENT_BONDS_AAA,
    EUR_GOVERNMENT_BONDS_ALL,
    GOVERNMENT_BONDS,
    build_curve_point,
    build_curve_set,
    curve_currency,
)
from desk_runtime.functions import utcnow
from desk_domain.providers import ECB

YC_TENORS = (
    ("3M", Decimal("0.25"), "SR_3M"),
    ("6M", Decimal("0.5"), "SR_6M"),
    ("1Y", Decimal(1), "SR_1Y"),
    ("2Y", Decimal(2), "SR_2Y"),
    ("3Y", Decimal(3), "SR_3Y"),
    ("5Y", Decimal(5), "SR_5Y"),
    ("7Y", Decimal(7), "SR_7Y"),
    ("10Y", Decimal(10), "SR_10Y"),
    ("15Y", Decimal(15), "SR_15Y"),
    ("20Y", Decimal(20), "SR_20Y"),
    ("30Y", Decimal(30), "SR_30Y"),
)
YC_DATASETS = {
    EUR_GOVERNMENT_BONDS_AAA: "G_N_A",
    EUR_GOVERNMENT_BONDS_ALL: "G_N_C",
}
MIN_CURVE_POINTS = 8


def _as_of(date_text):
    return datetime.strptime(date_text, "%Y-%m-%d").date()


def _tenor_rows(payload):
    rows = {}
    for row in payload.get("rows", []):
        code = row.get("DATA_TYPE_FM") or row.get("KEY", "").rsplit(".", 1)[-1]
        if code and row.get("OBS_VALUE"):
            rows[code] = row
    return rows


def make_curve_builder(curve_name):
    dataset_key = YC_DATASETS[curve_name]

    def build(client, record_request):
        record_request()
        payload = client.yield_curve(dataset_key, [code for _, _, code in YC_TENORS])
        by_code = _tenor_rows(payload)
        points = []
        for label, years, code in YC_TENORS:
            row = by_code.get(code)
            if row is None:
                continue
            points.append(build_curve_point(
                label,
                years,
                row["OBS_VALUE"],
                row.get("KEY") or f"YC {dataset_key} {code}",
                _as_of(row["TIME_PERIOD"]),
            ))
        if (
            len(points) < MIN_CURVE_POINTS
            or min(point.tenor_years for point in points) > Decimal(1)
            or max(point.tenor_years for point in points) < Decimal(10)
        ):
            raise ProviderDataError(
                ECB,
                f"incomplete YC {dataset_key} curve: "
                f"{len(points)}/{len(YC_TENORS)} usable tenors",
            )
        return build_curve_set(
            provider=ECB,
            curve_name=curve_name,
            curve_basis=GOVERNMENT_BONDS,
            currency=curve_currency(curve_name),
            as_of_date=min(point.source_as_of for point in points),
            received_at=utcnow(),
            points=points,
            raw_payload=payload,
        )

    return build
