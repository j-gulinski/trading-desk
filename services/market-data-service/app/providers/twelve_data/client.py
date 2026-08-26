import json

from app.providers.base import (
    ProviderAuthError,
    ProviderDataError,
    ProviderClient,
    ProviderRateLimited,
)
from shared.providers import TWELVE_DATA


PAIR_ASSET_CLASSES = ("FX", "COMMODITY")


def _data_error_detail(message):
    normalized = message.lower()
    if "available starting with" in normalized or "not available with your plan" in normalized:
        return "symbol is not included in the configured provider plan"
    return message


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
        if _data_error_detail(message) != message:
            raise ProviderDataError(
                self.provider, _data_error_detail(message), response=payload
            )
        if code in (401, 403):
            raise ProviderAuthError(self.provider, message, response=payload)
        raise ProviderDataError(self.provider, message, response=payload)

    def _raise_for_status(self, error, body=None):
        if error.code == 404 and body:
            try:
                payload = json.loads(body)
            except (TypeError, ValueError):
                payload = None
            if isinstance(payload, dict):
                provider_message = str(payload.get("message") or "symbol not found")
                raise ProviderDataError(
                    self.provider,
                    _data_error_detail(provider_message),
                    response=payload,
                    http_status=error.code,
                )
        super()._raise_for_status(error, body)

    def quotes(self, provider_symbols):
        payload = self.get("/quote", {"symbol": ",".join(provider_symbols)})
        if len(provider_symbols) > 1 and isinstance(payload, dict):
            for quote in payload.values():
                if isinstance(quote, dict) and quote.get("status") == "error":
                    message = str(quote.get("message") or "quote unavailable")
                    quote["message"] = _data_error_detail(message)
        return payload

    def search(self, query):
        return self.get("/symbol_search", {"symbol": query, "outputsize": 30})
