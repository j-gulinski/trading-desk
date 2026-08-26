"""FRED runtime wiring: credentials, budget and the curves built from its series."""

from app.config import (
    FRED_API_KEY,
    FRED_BUDGET_PER_MINUTE,
    FRED_PLN_CURVE_REFETCH_SECONDS,
    FRED_PROVIDER_LIMIT_PER_MINUTE,
)
from app.curve_feed import CurveBuilder, CurveFeed
from app.provider_runtime import ProviderRuntime
from app.providers.fred.client import FredClient
from app.providers.fred.curves import build_pln_reference_curve, build_usd_government_curve
from shared.curves import (
    PLN_REFERENCE_PROJECTION_3M,
    USD_GOVERNMENT_BONDS,
    curve_names_for_provider,
)
from shared.providers import FRED

_BUILDERS = {
    USD_GOVERNMENT_BONDS: CurveBuilder(
        USD_GOVERNMENT_BONDS,
        build_usd_government_curve,
        request_cost=11,
    ),
    PLN_REFERENCE_PROJECTION_3M: CurveBuilder(
        PLN_REFERENCE_PROJECTION_3M,
        build_pln_reference_curve,
        refetch_seconds=FRED_PLN_CURVE_REFETCH_SECONDS,
        request_cost=2,
    ),
}

curve_feed = CurveFeed(
    FRED,
    ProviderRuntime(
        FRED,
        FRED_BUDGET_PER_MINUTE,
        bool(FRED_API_KEY),
        provider_minute_limit=FRED_PROVIDER_LIMIT_PER_MINUTE,
    ),
    FredClient(FRED_API_KEY),
    tuple(_BUILDERS[curve_name] for curve_name in curve_names_for_provider(FRED)),
    enabled=bool(FRED_API_KEY),
)
