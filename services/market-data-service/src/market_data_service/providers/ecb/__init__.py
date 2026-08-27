from market_data_service.providers.ecb import feed
from market_data_service.providers.registration import ProviderRegistration
from desk_domain.providers import ECB

registration = ProviderRegistration(
    name=ECB,
    quote_mode="table",
    quote_feed=feed,
    curve_feed=feed.curve_feed,
)
