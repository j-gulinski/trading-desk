from app.providers.ecb import feed
from app.providers.registration import ProviderRegistration
from shared.providers import ECB

registration = ProviderRegistration(
    name=ECB,
    quote_mode="table",
    quote_feed=feed,
    curve_feed=feed.curve_feed,
)
