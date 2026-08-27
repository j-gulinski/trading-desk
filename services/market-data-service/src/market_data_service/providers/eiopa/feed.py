"""EIOPA runtime wiring: monthly archive client and three risk-free curves."""

from market_data_service.config import (
    EIOPA_CURVE_REFETCH_SECONDS,
    EIOPA_REQUEST_BUDGET_PER_MINUTE,
)
from market_data_service.curve_feed import CurveBuilder, CurveFeed
from market_data_service.provider_runtime import ProviderRuntime
from market_data_service.providers.eiopa.client import EiopaClient
from market_data_service.providers.eiopa.curves import make_curve_builder
from desk_domain.curves import curve_names_for_provider
from desk_domain.providers import EIOPA

curve_feed = CurveFeed(
    EIOPA,
    ProviderRuntime(
        EIOPA,
        EIOPA_REQUEST_BUDGET_PER_MINUTE,
        True,
        keyless=True,
    ),
    EiopaClient(),
    tuple(
        CurveBuilder(
            curve_name,
            make_curve_builder(curve_name),
            refetch_seconds=EIOPA_CURVE_REFETCH_SECONDS,
            request_cost=2,
        )
        for curve_name in curve_names_for_provider(EIOPA)
    ),
)
