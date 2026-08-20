from app.clients.base import ProviderClient, ProviderDataError
from shared.providers import FINNHUB


class FinnhubClient(ProviderClient):
    provider = FINNHUB
    base_url = "https://finnhub.io/api/v1"

    def auth_params(self):
        return {"token": self.api_key}

    def classify_body(self, payload):
        if isinstance(payload, dict) and payload.get("error"):
            raise ProviderDataError(self.provider, str(payload["error"]))

    def quote(self, symbol):
        return self.get("/quote", {"symbol": symbol})

    def search(self, query):
        return self.get("/search", {"q": query, "exchange": "US"})

    def market_status(self):
        return self.get("/stock/market-status", {"exchange": "US"})
