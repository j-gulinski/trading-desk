from app.providers.eiopa.feed import curve_feed
from app.providers.registration import ProviderRegistration
from shared.providers import EIOPA

registration = ProviderRegistration(name=EIOPA, curve_feed=curve_feed)
