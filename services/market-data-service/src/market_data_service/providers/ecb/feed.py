from desk_runtime.functions import utcnow
from desk_domain.curves import curve_names_for_provider
from desk_runtime.logging_config import get_logger
from desk_domain.providers import ECB
from market_data_service.providers.base import ProviderDataError
from market_data_service.providers.ecb.client import EcbClient
from market_data_service.providers.ecb.curves import make_curve_builder
from market_data_service.providers.ecb.normalizer import normalize_rate
from market_data_service.config import ECB_WINDOW_END, ECB_WINDOW_START, SERVICE_NAME
from market_data_service.curve_feed import CurveBuilder, CurveFeed
from market_data_service.provider_runtime import ProviderRuntime
from market_data_service.official_fixing_feed import OfficialFixingFeed, PublicationCalendar

log = get_logger(SERVICE_NAME)


class EcbFixingFeed(OfficialFixingFeed):
    """ECB euro reference rates."""

    def fetch(self, symbols):
        received = utcnow()
        payload = self.client.exchange_rates({symbol[3:] for symbol in symbols})
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


_runtime = ProviderRuntime(ECB, keyless=True)
_client = EcbClient()

fixing_feed = EcbFixingFeed(
    ECB, _runtime, _client,
    PublicationCalendar("Europe/Berlin", ECB_WINDOW_START, ECB_WINDOW_END),
)
curve_feed = CurveFeed(
    ECB,
    _runtime,
    _client,
    tuple(
        CurveBuilder(curve_name, make_curve_builder(curve_name))
        for curve_name in curve_names_for_provider(ECB)
    ),
)
