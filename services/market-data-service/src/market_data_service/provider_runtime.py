import threading
import time

from desk_domain.audit import write_audit
from desk_runtime.functions import get_iso_timestamp
from desk_runtime.logging_config import get_logger
from market_data_service.budget import RequestBudget
from market_data_service.providers.base import (
    ProviderAuthError,
    ProviderDataError,
    ProviderError,
    ProviderRateLimited,
)
from market_data_service.config import (
    AUTH_FAILURE_COOLDOWN_SECONDS,
    RATE_LIMIT_DEFAULT_COOLDOWN_SECONDS,
    SERVICE_NAME,
    TRANSIENT_ERROR_BACKOFF_SECONDS,
)

log = get_logger(SERVICE_NAME)

DEGRADED_STATUSES = ("RATE_LIMITED", "AUTH_FAILED", "ERROR")


class ProviderRuntime:
    """Health of one provider: status, cooldown after failures and its request budget."""

    def __init__(self, provider, enabled=True, keyless=False, **limits):
        self.provider = provider
        self.enabled = enabled
        self.keyless = keyless
        self.budget = RequestBudget(provider, **limits)
        self._lock = threading.Lock()
        self._status = "STARTING" if enabled else "DISABLED"
        self._last_error = None if enabled else "API key is not set"
        self._last_success_at = None
        self._last_polled_at = None
        self._error_count = 0
        self._cooldown_until = 0.0
        self._market_open = None
        self._market_session = None

    def acquire(self, cost=1, calls=1):
        """Reserves budget for provider calls; returns the refusal reason or None."""
        refusal = self.budget.acquire(cost, calls)
        if refusal is None:
            with self._lock:
                self._last_polled_at = get_iso_timestamp()
        return refusal

    def cooldown_seconds_left(self):
        with self._lock:
            return self._cooldown_until - time.monotonic()

    def status(self):
        with self._lock:
            return self._status

    def unavailable(self):
        """The reason this provider cannot be polled right now, or None."""
        cooldown_left = self.cooldown_seconds_left()
        if cooldown_left > 0:
            return f"{self.provider} is {self.status()}: retry in {round(cooldown_left)}s"
        return None

    def guarded(self, work, unavailable_event, log_level="info", **context):
        """Runs one provider call, mapping its errors onto this runtime; returns (result, error)."""
        try:
            return work(), None
        except ProviderRateLimited as error:
            self.enter_cooldown(
                "RATE_LIMITED", "rate limited", error.detail,
                error.retry_after_seconds or RATE_LIMIT_DEFAULT_COOLDOWN_SECONDS,
                "PROVIDER_RATE_LIMITED", "WARNING",
            )
            return None, f"{self.provider} is rate limited"
        except ProviderAuthError as error:
            self.enter_cooldown(
                "AUTH_FAILED", "authentication failed", error.detail,
                AUTH_FAILURE_COOLDOWN_SECONDS, "PROVIDER_AUTH_FAILED", "ERROR",
            )
            return None, f"{self.provider} rejected the API key"
        except ProviderDataError as error:
            getattr(log, log_level)(unavailable_event, provider=self.provider,
                                    detail=error.detail, **context)
            return None, error.detail
        except ProviderError as error:
            self.transient_error(error.detail, TRANSIENT_ERROR_BACKOFF_SECONDS)
            return None, error.detail
        except Exception as error:
            detail = f"unexpected {type(error).__name__} while processing provider data"
            log.exception("provider_processing_failed", provider=self.provider, **context)
            self.transient_error(detail, TRANSIENT_ERROR_BACKOFF_SECONDS)
            return None, detail

    def set_market_status(self, is_open, session_name):
        with self._lock:
            self._market_open = is_open
            self._market_session = session_name

    def market_open(self):
        with self._lock:
            return self._market_open

    def record_success(self):
        with self._lock:
            previous = self._status
            self._status = "OK"
            self._last_error = None
            self._last_success_at = get_iso_timestamp()
        if previous in DEGRADED_STATUSES:
            write_audit(
                SERVICE_NAME,
                "PROVIDER_RECOVERED",
                f"{self.provider} serving quotes again after {previous}",
                entity_type="PROVIDER",
                entity_id=self.provider,
            )

    def restore_success(self, last_success_at):
        """Marks a starting provider healthy from its last stored observation."""
        with self._lock:
            if self._status == "STARTING":
                self._status = "OK"
                self._last_error = None
                self._last_success_at = last_success_at

    def enter_cooldown(self, status, label, detail, cooldown_seconds, event_type, severity):
        with self._lock:
            previous = self._status
            self._status = status
            self._last_error = detail
            self._error_count += 1
            self._cooldown_until = time.monotonic() + cooldown_seconds
        log.warning(
            "provider_cooldown",
            provider=self.provider,
            status=status,
            cooldown_seconds=cooldown_seconds,
            detail=detail,
        )
        if previous != status:
            write_audit(
                SERVICE_NAME,
                event_type,
                f"{self.provider} {label} — polling paused for {cooldown_seconds}s",
                entity_type="PROVIDER",
                entity_id=self.provider,
                severity=severity,
                payload={"cooldown_seconds": cooldown_seconds},
            )

    def transient_error(self, detail, backoff_seconds):
        with self._lock:
            previous = self._status
            self._status = "ERROR"
            self._last_error = detail
            self._error_count += 1
            self._cooldown_until = time.monotonic() + backoff_seconds
        log.warning("provider_request_failed", provider=self.provider, detail=detail)
        if previous != "ERROR":
            write_audit(
                SERVICE_NAME,
                "PROVIDER_UNAVAILABLE",
                f"{self.provider} request failed — retrying in {backoff_seconds}s",
                entity_type="PROVIDER",
                entity_id=self.provider,
                severity="WARNING",
                payload={"backoff_seconds": backoff_seconds},
            )

    def snapshot(self, active_symbols):
        with self._lock:
            state = {
                "status": self._status,
                "last_error": self._last_error,
                "last_success_at": self._last_success_at,
                "last_polled_at": self._last_polled_at,
                "error_count": self._error_count,
                "cooldown_seconds_left": max(
                    0, round(self._cooldown_until - time.monotonic())
                ),
                "market_open": self._market_open,
                "market_session": self._market_session,
            }
        return {
            **state,
            "keyless": self.keyless,
            "budget": self.budget.state(),
            "active_symbols": active_symbols,
        }
