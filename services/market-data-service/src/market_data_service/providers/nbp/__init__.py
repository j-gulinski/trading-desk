from market_data_service.providers.nbp import feed
from market_data_service.providers.registration import ProviderRegistration
from desk_domain.providers import NBP

registration = ProviderRegistration(name=NBP, quote_mode="table", quote_feed=feed)
