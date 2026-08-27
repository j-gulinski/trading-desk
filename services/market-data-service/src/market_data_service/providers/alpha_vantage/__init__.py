from market_data_service.providers.alpha_vantage import feed
from market_data_service.providers.alpha_vantage.normalizer import attach_search_result
from market_data_service.providers.registration import ProviderRegistration
from desk_domain.providers import ALPHA_VANTAGE


registration = ProviderRegistration(
    name=ALPHA_VANTAGE,
    quote_mode="symbol",
    quote_feed=feed,
    attach_search=attach_search_result,
)
