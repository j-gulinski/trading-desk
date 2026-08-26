from app.providers.fred.feed import curve_feed
from app.providers.registration import ProviderRegistration
from shared.providers import FRED

registration = ProviderRegistration(name=FRED, curve_feed=curve_feed)
