from shared.functions import utcnow
from shared.logging_config import get_logger
from shared.providers import NBP
from app import reference_set
from app.clients.base import ProviderDataError
from app.clients.nbp import NbpClient
from app.config import NBP_WINDOW_END, NBP_WINDOW_START, SERVICE_NAME
from app.normalizer import normalize_nbp_gold, normalize_nbp_rate
from app.provider_runtime import ProviderRuntime
from app.reference_calendar import PublicationCalendar
from app.reference_feed import ReferenceFeed

log = get_logger(SERVICE_NAME)

PROVIDER = NBP
runtime = ProviderRuntime(NBP, None, True, keyless=True)
_client = NbpClient()
_calendar = PublicationCalendar("Europe/Warsaw", NBP_WINDOW_START, NBP_WINDOW_END)


def _table_payload(response):
    if not isinstance(response, list) or not response:
        raise ProviderDataError(NBP, "empty table response")
    return response[0]


def _fetch(symbols):
    received = utcnow()
    quotes = []
    fx = [symbol for symbol in symbols if not reference_set.is_gold(symbol)]
    if fx:
        runtime.record_request()
        table = _table_payload(_client.table_a())
        for symbol in fx:
            try:
                quotes.append(normalize_nbp_rate(symbol, table, received))
            except ProviderDataError as error:
                log.info("reference_rate_unpublished", provider=NBP, symbol=symbol,
                         detail=error.detail)
    if any(reference_set.is_gold(symbol) for symbol in symbols):
        runtime.record_request()
        try:
            payload = _table_payload(_client.gold_price())
            quotes.append(normalize_nbp_gold(reference_set.NBP_GOLD_SYMBOL,
                                             payload, received))
        except ProviderDataError as error:
            log.info("reference_rate_unpublished", provider=NBP,
                     symbol=reference_set.NBP_GOLD_SYMBOL, detail=error.detail)
    if not quotes:
        raise ProviderDataError(NBP, "no reference fixings in response")
    return quotes


def _universe():
    return reference_set.nbp_symbols(reference_set.active_trade_currencies())


_feed = ReferenceFeed(NBP, runtime, _calendar, _universe, _fetch)

poll_loop = _feed.poll_loop
refresh_symbol = _feed.refresh_symbol
refresh_table = _feed.refresh_table
reload_active = _feed.reload_universe
active_symbols = _feed.active_symbols
runtime_snapshot = _feed.runtime_snapshot
