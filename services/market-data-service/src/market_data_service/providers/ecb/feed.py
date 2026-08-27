from desk_runtime.functions import utcnow
from desk_domain.curves import curve_names_for_provider
from desk_runtime.logging_config import get_logger
from desk_domain.providers import ECB
from market_data_service import official_fixing_set
from market_data_service.providers.base import ProviderDataError
from market_data_service.providers.ecb.client import EcbClient
from market_data_service.providers.ecb.curves import make_curve_builder
from market_data_service.providers.ecb.normalizer import normalize_rate
from market_data_service.config import ECB_WINDOW_END, ECB_WINDOW_START, SERVICE_NAME
from market_data_service.curve_feed import CurveBuilder, CurveFeed
from market_data_service.provider_runtime import ProviderRuntime
from market_data_service.reference_calendar import PublicationCalendar
from market_data_service.official_fixing_feed import OfficialFixingFeed

log = get_logger(SERVICE_NAME)

PROVIDER = ECB
runtime = ProviderRuntime(ECB, None, True, keyless=True)
_client = EcbClient()
_calendar = PublicationCalendar("Europe/Berlin", ECB_WINDOW_START, ECB_WINDOW_END)


def _fetch(symbols):
    received = utcnow()
    runtime.record_request()
    payload = _client.exchange_rates({symbol[3:] for symbol in symbols})
    quotes = []
    for symbol in symbols:
        try:
            quotes.append(normalize_rate(symbol, payload, received))
        except ProviderDataError as error:
            log.info("official_fixing_unpublished", provider=ECB, symbol=symbol,
                     detail=error.detail)
    if not quotes:
        raise ProviderDataError(ECB, "no reference fixings in response")
    return quotes


def _universe():
    return official_fixing_set.ecb_fixing_symbols(
        official_fixing_set.reportable_trade_currencies()
    )


_feed = OfficialFixingFeed(ECB, runtime, _calendar, _universe, _fetch)
_curve_feed = CurveFeed(
    ECB,
    runtime,
    _client,
    tuple(
        CurveBuilder(curve_name, make_curve_builder(curve_name))
        for curve_name in curve_names_for_provider(ECB)
    ),
)
curve_feed = _curve_feed

poll_loop = _feed.poll_loop
refresh_symbol = _feed.refresh_symbol
refresh_table = _feed.refresh_table
reload_active = _feed.reload_universe
active_symbols = _feed.active_symbols


def runtime_snapshot():
    return {
        **_feed.runtime_snapshot(),
        "curves": _curve_feed.curve_names(),
        "curve_strategy": _curve_feed.strategy(),
        "feeds": {
            "fixings": _feed.runtime_snapshot(),
            "curves": _curve_feed.runtime_snapshot(),
        },
    }
