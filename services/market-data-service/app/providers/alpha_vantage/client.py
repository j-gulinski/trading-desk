from app.providers.base import (
    ProviderAuthError,
    ProviderClient,
    ProviderDataError,
    ProviderRateLimited,
)
from shared.providers import ALPHA_VANTAGE


class AlphaVantageClient(ProviderClient):
    provider = ALPHA_VANTAGE
    base_url = "https://www.alphavantage.co"

    def auth_params(self):
        return {"apikey": self.api_key}

    def classify_body(self, payload):
        if not isinstance(payload, dict):
            raise ProviderDataError(self.provider, "response body must be an object")
        message = payload.get("Information") or payload.get("Note")
        if message:
            detail = str(message)
            if "api key" in detail.lower() and "invalid" in detail.lower():
                raise ProviderAuthError(
                    self.provider,
                    "provider rejected the API key",
                    response=payload,
                )
            raise ProviderRateLimited(
                self.provider,
                "provider returned a throttling notice",
                response=payload,
            )
        if payload.get("Error Message"):
            raise ProviderDataError(
                self.provider,
                "provider rejected the request",
                response=payload,
            )

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
