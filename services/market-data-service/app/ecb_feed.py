from shared.functions import utcnow
from shared.logging_config import get_logger
from shared.providers import ECB
from app import reference_set
from app.clients.base import ProviderDataError
from app.clients.ecb import EcbClient
from app.config import ECB_WINDOW_END, ECB_WINDOW_START, SERVICE_NAME
from app.normalizer import normalize_ecb_rate
from app.provider_runtime import ProviderRuntime
from app.reference_calendar import PublicationCalendar
from app.reference_feed import ReferenceFeed

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
            quotes.append(normalize_ecb_rate(symbol, payload, received))
        except ProviderDataError as error:
            log.info("reference_rate_unpublished", provider=ECB, symbol=symbol,
                     detail=error.detail)
    if not quotes:
        raise ProviderDataError(ECB, "no reference fixings in response")
    return quotes


def _universe():
    return reference_set.ecb_symbols(reference_set.active_trade_currencies())


_feed = ReferenceFeed(ECB, runtime, _calendar, _universe, _fetch)

poll_loop = _feed.poll_loop
refresh_symbol = _feed.refresh_symbol
refresh_table = _feed.refresh_table
reload_active = _feed.reload_universe
active_symbols = _feed.active_symbols
runtime_snapshot = _feed.runtime_snapshot
