from market_data_service.providers.registration import ProviderRegistration
from market_data_service.providers.twelve_data import feed
from market_data_service.providers.twelve_data.normalizer import normalize_search_results
from desk_domain.providers import TWELVE_DATA

registration = ProviderRegistration(
    name=TWELVE_DATA,
    quote_mode="symbol",
    quote_feed=feed,
    normalize_search=normalize_search_results,
)
