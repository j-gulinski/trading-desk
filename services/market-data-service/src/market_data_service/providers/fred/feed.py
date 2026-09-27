from market_data_service.config import (
    FRED_API_KEY,
    FRED_BUDGET_PER_MINUTE,
    FRED_PROVIDER_LIMIT_PER_MINUTE,
)
from market_data_service.curve_feed import CurveBuilder, CurveFeed
from market_data_service.provider_runtime import ProviderRuntime
from market_data_service.providers.fred.client import FredClient
from market_data_service.providers.fred.curves import DGS_SERIES, build_usd_government_curve
from desk_domain.curves import USD_GOVERNMENT_BONDS
from desk_domain.providers import FRED

curve_feed = CurveFeed(
    FRED,
    ProviderRuntime(
        FRED,
        bool(FRED_API_KEY),
        per_minute=FRED_BUDGET_PER_MINUTE,
        provider_minute_limit=FRED_PROVIDER_LIMIT_PER_MINUTE,
    ),
    FredClient(FRED_API_KEY),
    (
        CurveBuilder(
            USD_GOVERNMENT_BONDS,
            build_usd_government_curve,
            request_cost=len(DGS_SERIES),
        ),
    ),
)
