from abc import ABC, abstractmethod
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from market_data_service.config import REQUEST_TIMEOUT_SECONDS, SERVICE_NAME
from desk_runtime.logging_config import get_logger


log = get_logger(SERVICE_NAME)


class ProviderError(Exception):
    def __init__(self, provider, detail, http_status=None):
        super().__init__(f"{provider}: {detail}")
        self.provider = provider
        self.detail = detail
        self.http_status = http_status


class ProviderAuthError(ProviderError):
    pass


class ProviderRateLimited(ProviderError):
    def __init__(self, provider, detail, retry_after_seconds=None, http_status=None):
        super().__init__(provider, detail, http_status=http_status)
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


class ProviderClient(ABC):
    @property
    @abstractmethod
    def provider(self): ...

    @property
    @abstractmethod
    def base_url(self): ...

    timeout_seconds = REQUEST_TIMEOUT_SECONDS
    api_key_param = None

    def __init__(self, api_key=None):
        self.api_key = api_key

    def auth_params(self):
        return {self.api_key_param: self.api_key} if self.api_key_param and self.api_key else {}

    def decode_body(self, body):
        return json.loads(body)

    def classify_body(self, payload):
        return None

    def get(self, path, params=None):
        params = params or {}
        started = time.monotonic()
        query = urllib.parse.urlencode({**params, **self.auth_params()})
        status = None
        try:
            body, status = self._fetch(f"{self.base_url}{path}?{query}")
            payload = self.decode_body(body)
            self.classify_body(payload)
        except ValueError as error:
            failure = ProviderDataError(self.provider, "response body failed to decode")
            self._log_response(path, params, started, status, failure)
            raise failure from error
        except ProviderError as error:
            self._log_response(path, params, started, error.http_status or status, error)
            raise
        self._log_response(path, params, started, status)
        return payload

    def _log_response(self, path, params, started, status, error=None):
        fields = {
            "provider": self.provider,
            "method": "GET",
            "endpoint": path,
            "params": params,
            "http_status": status,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "outcome": "error" if error else "ok",
        }
        if error is None:
            log.info("provider_http_response", **fields)
        else:
            log.warning("provider_http_response", **fields, error_type=type(error).__name__)

    def _fetch(self, url):
        try:
            with urllib.request.urlopen(url, timeout=self.timeout_seconds) as response:
                return response.read(), response.status
        except urllib.error.HTTPError as error:
            self._raise_for_status(error, error.read())
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ProviderUnavailable(self.provider, str(error)) from error

    def _raise_for_status(self, error, body=None):
        if error.code in (401, 403):
            raise ProviderAuthError(self.provider, f"HTTP {error.code}", http_status=error.code)
        if error.code == 404:
            raise ProviderDataError(self.provider, "not found", http_status=error.code)
        if error.code == 429:
            raise ProviderRateLimited(
                self.provider,
                "HTTP 429",
                retry_after_seconds=_retry_after_seconds(error.headers),
                http_status=error.code,
            )
        raise ProviderError(self.provider, f"HTTP {error.code}", http_status=error.code)
