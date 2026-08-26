from app.providers.registration import ProviderRegistration
from app.providers.twelve_data import feed
from app.providers.twelve_data.normalizer import normalize_search_results
from shared.providers import TWELVE_DATA

registration = ProviderRegistration(
    name=TWELVE_DATA,
    quote_mode="symbol",
    quote_feed=feed,
    normalize_search=normalize_search_results,
)
