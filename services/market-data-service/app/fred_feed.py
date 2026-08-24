from shared.providers import FRED
from app import curve_builders
from app.clients.fred import FredClient
from app.config import (
    FRED_API_KEY,
    FRED_BUDGET_PER_MINUTE,
    FRED_PROVIDER_LIMIT_PER_MINUTE,
    FRED_WINDOW_END,
    FRED_WINDOW_START,
    OECD_REFETCH_SECONDS,
)
from app.curve_feed import CurveBuilder, CurveFeed
from app.provider_runtime import ProviderRuntime
from app.reference_calendar import PublicationCalendar

PROVIDER = FRED
runtime = ProviderRuntime(
    FRED,
    FRED_BUDGET_PER_MINUTE,
    bool(FRED_API_KEY),
    provider_minute_limit=FRED_PROVIDER_LIMIT_PER_MINUTE,
)
_client = FredClient(FRED_API_KEY)
_calendar = PublicationCalendar("America/New_York", FRED_WINDOW_START, FRED_WINDOW_END)

_feed = CurveFeed(FRED, runtime, _calendar, _client, (
    CurveBuilder(curve_builders.USD_TREASURY, curve_builders.build_usd_treasury),
    CurveBuilder(curve_builders.PLN_REF, curve_builders.build_pln_ref,
                 min_refetch_seconds=OECD_REFETCH_SECONDS),
))


def poll_loop():
    if not FRED_API_KEY:
        return
    _feed.poll_loop()


def refresh_symbol(symbol):
    return None, "FRED serves curves, not quotes — use /curves/refresh", 422


def refresh_curve(curve_name):
    if not FRED_API_KEY:
        return None, "FRED is disabled: no API key configured", 503
    return _feed.refresh_curve(curve_name)


def refresh_curves():
    if not FRED_API_KEY:
        return [], [{"provider": FRED, "curve": name,
                     "reason": "FRED is disabled: no API key configured"}
                    for name in _feed.curve_names()]
    return _feed.refresh_all()


def curve_names():
    return _feed.curve_names()


def reload_active():
    pass


def active_symbols():
    return []


def runtime_snapshot():
    return {
        **runtime.snapshot(active_symbols()),
        "curves": _feed.curve_names(),
        "strategy": _feed.strategy(),
    }
