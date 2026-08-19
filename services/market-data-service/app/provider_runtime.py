import threading
import time

from shared.audit import write_audit
from shared.functions import get_iso_timestamp
from shared.logging_config import get_logger
from app.budget import DailyLedger, TokenBucket
from app.config import SERVICE_NAME

log = get_logger(SERVICE_NAME)

DEGRADED_STATUSES = ("RATE_LIMITED", "AUTH_FAILED", "ERROR")


class ProviderRuntime:
    def __init__(self, provider, budget_per_minute, api_key_present):
        self.provider = provider
        self.bucket = TokenBucket(budget_per_minute, budget_per_minute / 60)
        self.ledger = DailyLedger()
        self._budget_per_minute = budget_per_minute
        self._lock = threading.Lock()
        self._status = "STARTING" if api_key_present else "DISABLED"
        self._last_error = None if api_key_present else "API key is not set"
        self._last_success_at = None
        self._cooldown_until = 0.0
        self._market_open = None
        self._market_session = None
        self._active = {}

    def try_take(self):
        return self.bucket.try_take()

    def record_request(self):
        self.ledger.record()

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
            self._status = "ERROR"
            self._last_error = detail
            self._cooldown_until = time.monotonic() + backoff_seconds
        log.warning("provider_request_failed", provider=self.provider, detail=detail)

    def snapshot(self, active_symbols):
        with self._lock:
            state = {
                "status": self._status,
                "last_error": self._last_error,
                "last_success_at": self._last_success_at,
                "cooldown_seconds_left": max(
                    0, round(self._cooldown_until - time.monotonic())
                ),
                "market_open": self._market_open,
                "market_session": self._market_session,
            }
        return {
            **state,
            "budget": {
                **self.bucket.state(),
                "budget_per_minute": self._budget_per_minute,
                **self.ledger.state(),
            },
            "active_symbols": active_symbols,
        }
