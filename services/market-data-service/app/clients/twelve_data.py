from app.clients.base import (
    ProviderAuthError,
    ProviderDataError,
    ProviderClient,
    ProviderRateLimited,
)
from shared.providers import TWELVE_DATA


PAIR_ASSET_CLASSES = ("FX", "COMMODITY")


class TwelveDataClient(ProviderClient):
    provider = TWELVE_DATA
    base_url = "https://api.twelvedata.com"

    @staticmethod
    def provider_symbol(symbol, asset_class):
        if asset_class in PAIR_ASSET_CLASSES and len(symbol) == 6:
            return f"{symbol[:3]}/{symbol[3:]}"
        return symbol

    def auth_params(self):
        return {"apikey": self.api_key} if self.api_key else {}

    def classify_body(self, payload):
        if not isinstance(payload, dict) or payload.get("status") != "error":
            return
        code = payload.get("code")
        message = str(payload.get("message") or f"error code {code}")
        if code == 429:
            raise ProviderRateLimited(self.provider, message, response=payload)
        if code in (401, 403):
            raise ProviderAuthError(self.provider, message, response=payload)
        raise ProviderDataError(self.provider, message, response=payload)

    def quotes(self, provider_symbols):
        return self.get("/quote", {"symbol": ",".join(provider_symbols)})

    def search(self, query):
        return self.get("/symbol_search", {"symbol": query, "outputsize": 30})
