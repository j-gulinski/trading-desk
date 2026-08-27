from market_data_service.providers.fred.feed import curve_feed
from market_data_service.providers.registration import ProviderRegistration
from desk_domain.providers import FRED

registration = ProviderRegistration(name=FRED, curve_feed=curve_feed)
