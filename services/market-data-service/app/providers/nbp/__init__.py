from app.providers.nbp import feed
from app.providers.registration import ProviderRegistration
from shared.providers import NBP

registration = ProviderRegistration(name=NBP, quote_mode="table", quote_feed=feed)
