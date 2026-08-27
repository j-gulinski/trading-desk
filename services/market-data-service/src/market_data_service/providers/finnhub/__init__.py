from market_data_service.providers.finnhub import feed
from market_data_service.providers.finnhub.normalizer import normalize_search_results
from market_data_service.providers.registration import ProviderRegistration
from desk_domain.providers import FINNHUB

registration = ProviderRegistration(
    name=FINNHUB,
    quote_mode="symbol",
    quote_feed=feed,
    normalize_search=normalize_search_results,
)
