from market_data_service.providers.base import (
    ProviderAuthError,
    ProviderClient,
    ProviderDataError,
    ProviderRateLimited,
)
from market_data_service.config import ALPHA_VANTAGE_BASE_URL
from desk_domain.providers import ALPHA_VANTAGE


class AlphaVantageClient(ProviderClient):
    provider = ALPHA_VANTAGE
    base_url = ALPHA_VANTAGE_BASE_URL

    api_key_param = "apikey"

    def classify_body(self, payload):
        if not isinstance(payload, dict):
            raise ProviderDataError(self.provider, "response body must be an object")
        message = payload.get("Information") or payload.get("Note")
        if message:
            detail = str(message)
            if "api key" in detail.lower() and "invalid" in detail.lower():
                raise ProviderAuthError(self.provider, "provider rejected the API key")
            raise ProviderRateLimited(self.provider, "provider returned a throttling notice")
        if payload.get("Error Message"):
            raise ProviderDataError(self.provider, "provider rejected the request")

    def quote(self, symbol, asset_class):
        if asset_class == "EQUITY":
            return self.get("/query", {"function": "GLOBAL_QUOTE", "symbol": symbol})
        if asset_class == "FX" and len(symbol) == 6:
            return self.get(
                "/query",
                {
                    "function": "CURRENCY_EXCHANGE_RATE",
                    "from_currency": symbol[:3],
                    "to_currency": symbol[3:],
                },
            )
        raise ProviderDataError(
            self.provider,
            f"{asset_class} symbol {symbol} is not supported by this adapter",
        )
