from market_data_service.providers.base import (
    ProviderAuthError,
    ProviderClient,
    ProviderDataError,
    ProviderRateLimited,
)
from desk_domain.providers import FRED


class FredClient(ProviderClient):
    provider = FRED
    base_url = "https://api.stlouisfed.org/fred"

    def auth_params(self):
        return {"api_key": self.api_key or "", "file_type": "json"}

    def classify_body(self, payload):
        if not isinstance(payload, dict) or "error_message" not in payload:
            return
        code = payload.get("error_code")
        message = str(payload.get("error_message"))
        if code == 429:
            raise ProviderRateLimited(self.provider, message, response=payload)
        if code in (400, 401, 403) and "api_key" in message:
            raise ProviderAuthError(self.provider, message, response=payload)
        raise ProviderDataError(self.provider, message, response=payload)

    def _raise_for_status(self, error, body=None):
        # FRED answers HTTP 400 for a bad/unregistered key — an auth fact, not a data one
        if error.code == 400 and body and b"api_key" in body:
            raise ProviderAuthError(
                self.provider,
                body.decode("utf-8", errors="replace"),
                http_status=error.code,
            )
        super()._raise_for_status(error, body)

    def latest_observations(self, series_id, limit):
        return self.get(
            "/series/observations",
            {"series_id": series_id, "sort_order": "desc", "limit": limit},
        )
