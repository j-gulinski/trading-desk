from desk_runtime.functions import utcnow
from desk_runtime.logging_config import get_logger
from desk_domain.providers import NBP
from market_data_service.official_fixing_set import NBP_GOLD_SYMBOL, is_gold
from market_data_service.providers.base import ProviderDataError
from market_data_service.providers.nbp.client import NbpClient
from market_data_service.providers.nbp.normalizer import normalize_gold, normalize_rate
from market_data_service.config import NBP_WINDOW_END, NBP_WINDOW_START, SERVICE_NAME
from market_data_service.provider_runtime import ProviderRuntime
from market_data_service.official_fixing_feed import OfficialFixingFeed, PublicationCalendar

log = get_logger(SERVICE_NAME)


def _table_payload(response):
    if not isinstance(response, list) or not response:
        raise ProviderDataError(NBP, "empty table response")
    return response[0]


class NbpFixingFeed(OfficialFixingFeed):
    """NBP table A mid rates against PLN and the NBP gold fixing."""

    def request_cost(self, symbols):
        fx_table = any(not is_gold(symbol) for symbol in symbols)
        gold = any(is_gold(symbol) for symbol in symbols)
        return fx_table + gold

    def fetch(self, symbols):
        received = utcnow()
        quotes = []
        fx = [symbol for symbol in symbols if not is_gold(symbol)]
        if fx:
            table = _table_payload(self.client.table_a())
            for symbol in fx:
                try:
                    quotes.append(normalize_rate(symbol, table, received))
                except ProviderDataError as error:
                    log.info("official_fixing_unpublished", provider=NBP, symbol=symbol,
                             detail=error.detail)
        if any(is_gold(symbol) for symbol in symbols):
            try:
                payload = _table_payload(self.client.gold_price())
                quotes.append(normalize_gold(NBP_GOLD_SYMBOL, payload, received))
            except ProviderDataError as error:
                log.info("official_fixing_unpublished", provider=NBP,
                         symbol=NBP_GOLD_SYMBOL, detail=error.detail)
        if not quotes:
            raise ProviderDataError(NBP, "no reference fixings in response")
        return quotes


feed = NbpFixingFeed(
    NBP,
    ProviderRuntime(NBP, keyless=True),
    NbpClient(),
    PublicationCalendar("Europe/Warsaw", NBP_WINDOW_START, NBP_WINDOW_END),
)
