"""EIOPA runtime wiring: monthly archive client and three risk-free curves."""

from app.config import (
    EIOPA_CURVE_REFETCH_SECONDS,
    EIOPA_REQUEST_BUDGET_PER_MINUTE,
)
from app.curve_feed import CurveBuilder, CurveFeed
from app.provider_runtime import ProviderRuntime
from app.providers.eiopa.client import EiopaClient
from app.providers.eiopa.curves import make_curve_builder
from shared.curves import curve_names_for_provider
from shared.providers import EIOPA

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
