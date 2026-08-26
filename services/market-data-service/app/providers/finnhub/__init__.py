from app.providers.finnhub import feed
from app.providers.finnhub.normalizer import normalize_search_results
from app.providers.registration import ProviderRegistration
from shared.providers import FINNHUB

registration = ProviderRegistration(
    name=FINNHUB,
    quote_mode="symbol",
    quote_feed=feed,
    normalize_search=normalize_search_results,
)
