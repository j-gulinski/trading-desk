from shared.functions import utcnow
from shared.logging_config import get_logger
from shared.providers import NBP
from app import official_fixing_set
from app.providers.base import ProviderDataError
from app.providers.nbp.client import NbpClient
from app.providers.nbp.normalizer import normalize_gold, normalize_rate
from app.config import NBP_WINDOW_END, NBP_WINDOW_START, SERVICE_NAME
from app.provider_runtime import ProviderRuntime
from app.reference_calendar import PublicationCalendar
from app.official_fixing_feed import OfficialFixingFeed

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
    fx = [symbol for symbol in symbols if not official_fixing_set.is_gold(symbol)]
    if fx:
        runtime.record_request()
        table = _table_payload(_client.table_a())
        for symbol in fx:
            try:
                quotes.append(normalize_rate(symbol, table, received))
            except ProviderDataError as error:
                log.info("official_fixing_unpublished", provider=NBP, symbol=symbol,
                         detail=error.detail)
    if any(official_fixing_set.is_gold(symbol) for symbol in symbols):
        runtime.record_request()
        try:
            payload = _table_payload(_client.gold_price())
            quotes.append(normalize_gold(official_fixing_set.NBP_GOLD_SYMBOL,
                                         payload, received))
        except ProviderDataError as error:
            log.info("official_fixing_unpublished", provider=NBP,
                     symbol=official_fixing_set.NBP_GOLD_SYMBOL, detail=error.detail)
    if not quotes:
        raise ProviderDataError(NBP, "no reference fixings in response")
    return quotes


def _universe():
    return official_fixing_set.nbp_fixing_symbols(
        official_fixing_set.reportable_trade_currencies()
    )


_feed = OfficialFixingFeed(NBP, runtime, _calendar, _universe, _fetch)
poll_loop = _feed.poll_loop
refresh_symbol = _feed.refresh_symbol
refresh_table = _feed.refresh_table
reload_active = _feed.reload_universe
active_symbols = _feed.active_symbols


def runtime_snapshot():
    return _feed.runtime_snapshot()
