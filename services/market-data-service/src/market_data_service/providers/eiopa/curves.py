"""Build EIOPA risk-free curves from the provider's monthly workbook release."""

import re
from decimal import Decimal

from market_data_service.providers.base import ProviderDataError
from market_data_service.providers.eiopa.workbook import read_term_structure
from desk_domain.curves import (
    EUR_RISK_FREE,
    GOVERNMENT_BONDS,
    INTEREST_RATE_SWAPS,
    OVERNIGHT_INDEX,
    PLN_RISK_FREE,
    USD_RISK_FREE,
    build_curve_point,
    build_curve_set,
    curve_currency,
)
from desk_runtime.functions import utcnow
from desk_domain.providers import EIOPA

WORKBOOK_COUNTRY_BY_CURVE = {
    EUR_RISK_FREE: "Euro",
    USD_RISK_FREE: "United States",
    PLN_RISK_FREE: "Poland",
}
TENORS = (1, 2, 3, 5, 7, 10, 15, 20, 30)
BASES = {
    "SWP": INTEREST_RATE_SWAPS,
    "OIS": OVERNIGHT_INDEX,
    "GOV": GOVERNMENT_BONDS,
}
DERIVATION = re.compile(r"_(SWP|OIS|GOV)_")


def _derivation(series_code):
    match = DERIVATION.search(series_code)
    return match.group(1) if match else None


def make_curve_builder(curve_name):
    country = WORKBOOK_COUNTRY_BY_CURVE[curve_name]

    def build(client, record_request):
        record_request()
        release = client.latest_release()
        archive, fetched = client.monthly_archive(release["href"])
        if fetched:
            record_request()
        published = read_term_structure(archive, country, TENORS)
        basis = BASES.get(_derivation(published["series_code"]))
        if basis is None:
            raise ProviderDataError(
                EIOPA, f"{published['series_code']} states an unhandled derivation"
            )
        liquid_to = published["last_liquid_point"]
        points = []
        for years in TENORS:
            extrapolated = liquid_to is not None and years > liquid_to
            points.append(build_curve_point(
                f"{years}Y",
                Decimal(years),
                published["rates"][years],
                None if extrapolated else published["series_code"],
                None if extrapolated else published["as_of_date"],
            ))
        return build_curve_set(
            provider=EIOPA,
            curve_name=curve_name,
            curve_basis=basis,
            currency=curve_currency(curve_name),
            as_of_date=published["as_of_date"],
            received_at=utcnow(),
            points=points,
            raw_payload={
                "release": release["href"].rsplit("=", 1)[-1],
                "series_code": published["series_code"],
                "last_liquid_point_years": liquid_to,
                "ultimate_forward_rate_percent": published["ultimate_forward_rate"],
                "credit_risk_adjustment_basis_points": published["credit_risk_adjustment"],
                "rates_percent": {
                    str(years): str(rate) for years, rate in published["rates"].items()
                },
            },
        )

    return build
