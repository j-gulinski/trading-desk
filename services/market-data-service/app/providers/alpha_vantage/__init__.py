from app.providers.alpha_vantage import feed
from app.providers.alpha_vantage.normalizer import attach_search_result
from app.providers.registration import ProviderRegistration
from shared.providers import ALPHA_VANTAGE


registration = ProviderRegistration(
    name=ALPHA_VANTAGE,
    quote_mode="symbol",
    quote_feed=feed,
    attach_search=attach_search_result,
)
