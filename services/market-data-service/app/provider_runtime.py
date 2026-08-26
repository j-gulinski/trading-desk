import threading
import time

from shared.active_set import load_active_set
from shared.audit import write_audit
from shared.functions import get_iso_timestamp
from shared.logging_config import get_logger
from app.budget import DailyLedger, RollingMinuteBudget
from app.quote_cleanup import cleanup_active_drops
from app.providers.base import (
    ProviderAuthError,
    ProviderDataError,
    ProviderError,
    ProviderRateLimited,
)
from app.config import (
    ACTIVE_SET_REFRESH_SECONDS,
    AUTH_FAILURE_COOLDOWN_SECONDS,
    PROVIDER_ACTIVE_WINDOW_HOURS,
    PROVIDER_BUDGET_USAGE_PERCENT,
    RATE_LIMIT_DEFAULT_COOLDOWN_SECONDS,
    SERVICE_NAME,
    TRANSIENT_ERROR_BACKOFF_SECONDS,
)

log = get_logger(SERVICE_NAME)

DEGRADED_STATUSES = ("RATE_LIMITED", "AUTH_FAILED", "ERROR")


class ProviderRuntime:
    def __init__(
        self,
        provider,
        budget_per_minute,
        api_key_present,
        daily_budget=None,
        provider_minute_limit=None,
        provider_daily_limit=None,
        keyless=False,
    ):
        self.provider = provider
        self.keyless = keyless
        self.bucket = (
            RollingMinuteBudget(budget_per_minute)
            if budget_per_minute is not None else None
        )
        self.ledger = DailyLedger(daily_budget, provider_daily_limit)
        self._budget_per_minute = budget_per_minute
        self._provider_minute_limit = provider_minute_limit
        self._lock = threading.Lock()
        self._status = "STARTING" if api_key_present else "DISABLED"
        self._last_error = None if api_key_present else "API key is not set"
        self._last_success_at = None
        self._last_polled_at = None
        self._error_count = 0
        self._cooldown_until = 0.0
        self._market_open = None
        self._market_session = None
        self._active = {}
        self._active_loaded_at = None

    def try_take(self, cost=1):
        return True if self.bucket is None else self.bucket.try_take(cost)

    def budget_wait_seconds(self, cost=1):
        return 0 if self.bucket is None else self.bucket.seconds_until_available(cost)

    def record_request(self, credits=1):
        self.ledger.record(credits)
        with self._lock:
            self._last_polled_at = get_iso_timestamp()

    def cooldown_seconds_left(self):
        with self._lock:
            return self._cooldown_until - time.monotonic()

    def status(self):
        with self._lock:
            return self._status

    def set_active(self, entries):
        with self._lock:
            self._active = entries

    def active_entries(self):
        with self._lock:
            return list(self._active.values())

    def active_entry(self, symbol):
        with self._lock:
            return self._active.get(symbol)

    def pollable_entries(self):
        return [entry for entry in self.active_entries() if entry.serves(self.provider)]

    def reload_active(self):
        fresh = load_active_set()
        with self._lock:
            previous = self._active
            self._active = fresh
            self._active_loaded_at = time.monotonic()
        cleanup_active_drops(self.provider, previous, fresh)

    def reload_active_if_stale(self):
        """False when the reload failed — the caller should back off and retry."""
        with self._lock:
            loaded_at = self._active_loaded_at
        if loaded_at is not None and time.monotonic() - loaded_at < ACTIVE_SET_REFRESH_SECONDS:
            return True
        try:
            self.reload_active()
        except Exception:
            log.exception("active_set_load_failed", provider=self.provider)
            return False
        return True

    def resolve(self, symbol):
        """The active entry this provider serves, reloading the set once if it is missing.
        Returns (entry, error, http_status)."""
        entry = self.active_entry(symbol)
        if entry is None:
            self.reload_active()
            entry = self.active_entry(symbol)
        if entry is None:
            return None, "symbol is not in the active set", 404
        if not entry.serves(self.provider):
            return None, f"{self.provider} is not watching {symbol}", 422
        return entry, None, 200

    def unavailable(self):
        """The reason this provider cannot be polled right now, or None."""
        cooldown_left = self.cooldown_seconds_left()
        if cooldown_left > 0:
            return f"{self.provider} is {self.status()}: retry in {round(cooldown_left)}s"
        return None

    def guarded(self, work, unavailable_event, log_level="info", **context):
        """Runs one provider call, mapping every provider error onto this runtime's
        state. Returns (result, error message)."""
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
            log.exception(
                "provider_processing_failed",
                provider=self.provider,
                **context,
            )
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
                payload={"detail": detail, "cooldown_seconds": cooldown_seconds},
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
                "PROVIDER_FETCH_FAILED",
                f"{self.provider} request failed — retrying in {backoff_seconds}s",
                entity_type="PROVIDER",
                entity_id=self.provider,
                severity="WARNING",
                payload={"detail": detail, "backoff_seconds": backoff_seconds},
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
        if self.bucket is None:
            budget = self.ledger.state()
        else:
            budget = {
                **self.bucket.state(),
                "budget_per_minute": self._budget_per_minute,
                **self.ledger.state(),
            }
            if self._provider_minute_limit is not None:
                budget["provider_minute_limit"] = self._provider_minute_limit
                budget["usage_percent"] = PROVIDER_BUDGET_USAGE_PERCENT
            if "daily_budget" in budget:
                budget["active_window_hours"] = PROVIDER_ACTIVE_WINDOW_HOURS
        return {
            **state,
            "keyless": self.keyless,
            "budget": budget,
            "active_symbols": active_symbols,
        }
