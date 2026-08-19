import json
import time
import urllib.error
import urllib.parse
import urllib.request

from app.config import REQUEST_TIMEOUT_SECONDS


class ProviderError(Exception):
    def __init__(self, provider, detail):
        super().__init__(f"{provider}: {detail}")
        self.provider = provider
        self.detail = detail


class ProviderAuthError(ProviderError):
    pass


class ProviderRateLimited(ProviderError):
    def __init__(self, provider, detail, retry_after_seconds=None):
        super().__init__(provider, detail)
        self.retry_after_seconds = retry_after_seconds


class ProviderUnavailable(ProviderError):
    pass


class ProviderDataError(ProviderError):
    pass


def _retry_after_seconds(headers):
    raw = headers.get("Retry-After") if headers else None
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


class ProviderClient:
    provider = None
    base_url = None

    def __init__(self, api_key=None):
        self.api_key = api_key

    def auth_params(self):
        return {}

    def classify_body(self, payload):
        pass

    def get(self, path, params=None):
        query = urllib.parse.urlencode({**(params or {}), **self.auth_params()})
        body = self._fetch(f"{self.base_url}{path}?{query}")
        try:
            payload = json.loads(body)
        except ValueError:
            raise ProviderDataError(self.provider, "response body is not JSON")
        self.classify_body(payload)
        return payload

    def _fetch(self, url, retries=1):
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                self._raise_for_status(error)
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                if attempt == retries:
                    raise ProviderUnavailable(self.provider, str(error))
                time.sleep(1)

    def _raise_for_status(self, error):
        if error.code in (401, 403):
            raise ProviderAuthError(self.provider, f"HTTP {error.code}")
        if error.code == 429:
            raise ProviderRateLimited(
                self.provider,
                "HTTP 429",
                retry_after_seconds=_retry_after_seconds(error.headers),
            )
        raise ProviderError(self.provider, f"HTTP {error.code}")
