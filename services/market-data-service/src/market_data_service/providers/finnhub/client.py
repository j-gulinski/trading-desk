from market_data_service.providers.base import ProviderClient, ProviderDataError
from desk_domain.providers import FINNHUB


class FinnhubClient(ProviderClient):
    provider = FINNHUB
    base_url = "https://finnhub.io/api/v1"

    api_key_param = "token"

    def classify_body(self, payload):
        if isinstance(payload, dict) and payload.get("error"):
            raise ProviderDataError(
                self.provider, str(payload["error"]), response=payload
            )

    def quote(self, symbol):
        return self.get("/quote", {"symbol": symbol})

    def search(self, query):
        return self.get("/search", {"q": query, "exchange": "US"})

    def market_status(self):
        return self.get("/stock/market-status", {"exchange": "US"})
