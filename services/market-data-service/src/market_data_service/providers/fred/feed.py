from market_data_service.config import (
    FRED_API_KEY,
    FRED_BUDGET_PER_MINUTE,
    FRED_PROVIDER_LIMIT_PER_MINUTE,
)
from market_data_service.curve_feed import CurveBuilder, CurveFeed
from market_data_service.provider_runtime import ProviderRuntime
from market_data_service.providers.fred.client import FredClient
from market_data_service.providers.fred.curves import build_usd_government_curve
from desk_domain.curves import (
    USD_GOVERNMENT_BONDS,
    curve_names_for_provider,
)
from desk_domain.providers import FRED

_BUILDERS = {
    USD_GOVERNMENT_BONDS: CurveBuilder(
        USD_GOVERNMENT_BONDS,
        build_usd_government_curve,
        request_cost=11,
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
