from shared.functions import utcnow
from shared.logging_config import get_logger
from shared.providers import ECB
from app import curve_builders, reference_set
from app.clients.base import ProviderDataError
from app.clients.ecb import EcbClient
from app.config import (
    ECB_WINDOW_END,
    ECB_WINDOW_START,
    ECB_YC_WINDOW_END,
    ECB_YC_WINDOW_START,
    SERVICE_NAME,
)
from app.curve_feed import CurveBuilder, CurveFeed
from app.normalizer import normalize_ecb_rate
from app.provider_runtime import ProviderRuntime
from app.reference_calendar import PublicationCalendar
from app.reference_feed import ReferenceFeed

log = get_logger(SERVICE_NAME)

PROVIDER = ECB
runtime = ProviderRuntime(ECB, None, True, keyless=True)
_client = EcbClient()
_calendar = PublicationCalendar("Europe/Berlin", ECB_WINDOW_START, ECB_WINDOW_END)
_yc_calendar = PublicationCalendar(
    "Europe/Berlin", ECB_YC_WINDOW_START, ECB_YC_WINDOW_END
)


def _fetch(symbols):
    received = utcnow()
    runtime.record_request()
    payload = _client.exchange_rates({symbol[3:] for symbol in symbols})
    quotes = []
    for symbol in symbols:
        try:
            quotes.append(normalize_ecb_rate(symbol, payload, received))
        except ProviderDataError as error:
            log.info("reference_rate_unpublished", provider=ECB, symbol=symbol,
                     detail=error.detail)
    if not quotes:
        raise ProviderDataError(ECB, "no reference fixings in response")
    return quotes


def _universe():
    return reference_set.ecb_symbols(reference_set.active_trade_currencies())


def _backfill(symbols, days):
    received = utcnow()
    runtime.record_request()
    payload = _client.exchange_rates({symbol[3:] for symbol in symbols},
                                     last_observations=days)
    by_date = {}
    for row in payload.get("rows", []):
        by_date.setdefault(row.get("TIME_PERIOD"), []).append(row)
    quotes = []
    for date_text in sorted(filter(None, by_date)):
        day_payload = {"format": "csvdata", "rows": by_date[date_text]}
        for symbol in symbols:
            try:
                quotes.append(normalize_ecb_rate(symbol, day_payload, received))
            except ProviderDataError:
                continue
    return quotes


_feed = ReferenceFeed(ECB, runtime, _calendar, _universe, _fetch, _backfill)
_curve_feed = CurveFeed(ECB, runtime, _yc_calendar, _client, (
    CurveBuilder(curve_builders.EUR_GOV_AAA,
                 curve_builders.make_ecb_curve_builder(curve_builders.EUR_GOV_AAA)),
    CurveBuilder(curve_builders.EUR_GOV_ALL,
                 curve_builders.make_ecb_curve_builder(curve_builders.EUR_GOV_ALL)),
))

poll_loop = _feed.poll_loop
poll_loops = (_feed.poll_loop, _curve_feed.poll_loop)
refresh_symbol = _feed.refresh_symbol
refresh_table = _feed.refresh_table
refresh_curve = _curve_feed.refresh_curve
refresh_curves = _curve_feed.refresh_all
curve_names = _curve_feed.curve_names
reload_active = _feed.reload_universe
active_symbols = _feed.active_symbols


def runtime_snapshot():
    return {
        **_feed.runtime_snapshot(),
        "curves": _curve_feed.curve_names(),
        "curve_strategy": _curve_feed.strategy(),
    }
