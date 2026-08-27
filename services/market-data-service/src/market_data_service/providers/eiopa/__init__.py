from market_data_service.providers.eiopa.feed import curve_feed
from market_data_service.providers.registration import ProviderRegistration
from desk_domain.providers import EIOPA

registration = ProviderRegistration(name=EIOPA, curve_feed=curve_feed)
