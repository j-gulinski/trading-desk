"""HTTP transport and typed failures shared by all provider packages."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from app.config import REQUEST_TIMEOUT_SECONDS, SERVICE_NAME
from shared.logging_config import get_logger


log = get_logger(SERVICE_NAME)


class ProviderError(Exception):
    def __init__(self, provider, detail, response=None, http_status=None):
        super().__init__(f"{provider}: {detail}")
        self.provider = provider
        self.detail = detail
        self.response = response
        self.http_status = http_status


class ProviderAuthError(ProviderError):
    pass


class ProviderRateLimited(ProviderError):
    def __init__(
        self,
        provider,
        detail,
        retry_after_seconds=None,
        response=None,
        http_status=None,
    ):
        super().__init__(
            provider, detail, response=response, http_status=http_status
        )
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
    timeout_seconds = REQUEST_TIMEOUT_SECONDS

    def __init__(self, api_key=None):
        self.api_key = api_key

    def auth_params(self):
        return {}

    def decode_body(self, body):
        return json.loads(body)

    def classify_body(self, payload):
        return None

    def get(self, path, params=None):
        public_params = params or {}
        request_fields = self._request_fields(path, public_params)
        started = time.monotonic()
        query = urllib.parse.urlencode({**public_params, **self.auth_params()})
        status = None
        body = None
        payload = None
        try:
            body, status = self._fetch(f"{self.base_url}{path}?{query}")
            payload = self.decode_body(body)
            self.classify_body(payload)
        except ValueError as error:
            provider_error = ProviderDataError(self.provider, "response body failed to decode")
            raw_response = body.decode("utf-8", errors="replace") if body else None
            self._log_response(
                request_fields,
                started,
                status,
                response_payload=raw_response,
                error=provider_error,
            )
            raise provider_error from error
        except ProviderError as error:
            status = error.http_status or status
            self._log_response(
                request_fields,
                started,
                status,
                response_payload=error.response if error.response is not None else payload,
                error=error,
            )
            raise
        self._log_response(
            request_fields,
            started,
            status,
            result_count=self._result_count(path, public_params, payload),
            response_payload=payload,
        )
        return payload

    def _request_fields(self, path, params):
        fields = {"provider": self.provider, "method": "GET", "endpoint": path}
        if path in ("/search", "/symbol_search"):
            fields["query"] = params.get("q") or params.get("symbol")
        elif params.get("symbol"):
            symbols = [symbol for symbol in str(params["symbol"]).split(",") if symbol]
            fields["symbols"] = symbols
            fields["symbol_count"] = len(symbols)
        return fields

    @staticmethod
    def _result_count(path, params, payload):
        if path in ("/search", "/symbol_search"):
            key = "result" if path == "/search" else "data"
            results = payload.get(key) if isinstance(payload, dict) else None
            return len(results) if isinstance(results, list) else 0
        if path == "/quote":
            requested = [value for value in str(params.get("symbol") or "").split(",") if value]
            if len(requested) <= 1:
                return 1 if isinstance(payload, dict) and payload else 0
            return sum(
                isinstance(payload.get(symbol), dict)
                for symbol in requested
            ) if isinstance(payload, dict) else 0
        return None

    @staticmethod
    def _log_response(
        request_fields,
        started,
        status,
        result_count=None,
        response_payload=None,
        error=None,
    ):
        fields = {
            **request_fields,
            "http_status": status,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "outcome": "error" if error else "ok",
        }
        if response_payload is not None:
            fields["response_json"] = (
                response_payload
                if isinstance(response_payload, str)
                else json.dumps(response_payload, separators=(",", ":"), default=str)
            )
        if result_count is not None:
            fields["result_count"] = result_count
        if error is not None:
            fields["error_type"] = type(error).__name__
            fields["error"] = error.detail
            log.warning("provider_http_response", **fields)
        else:
            log.info("provider_http_response", **fields)

    def _fetch(self, url, retries=0):
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(url, timeout=self.timeout_seconds) as response:
                    return response.read(), response.status
            except urllib.error.HTTPError as error:
                self._raise_for_status(error, error.read())
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                if attempt == retries:
                    raise ProviderUnavailable(self.provider, str(error))
                time.sleep(1)

    def _raise_for_status(self, error, body=None):
        try:
            error_response = json.loads(body) if body else None
        except (TypeError, ValueError):
            error_response = body.decode("utf-8", errors="replace") if body else None
        if error.code in (401, 403):
            raise ProviderAuthError(
                self.provider,
                f"HTTP {error.code}",
                response=error_response,
                http_status=error.code,
            )
        if error.code == 404:
            raise ProviderDataError(
                self.provider,
                "not found",
                response=error_response,
                http_status=error.code,
            )
        if error.code == 429:
            raise ProviderRateLimited(
                self.provider,
                "HTTP 429",
                retry_after_seconds=_retry_after_seconds(error.headers),
                response=error_response,
                http_status=error.code,
            )
        raise ProviderError(
            self.provider,
            f"HTTP {error.code}",
            response=error_response,
            http_status=error.code,
        )
