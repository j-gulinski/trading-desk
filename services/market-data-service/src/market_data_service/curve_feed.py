import time
from dataclasses import dataclass
from typing import Callable

from desk_domain.curves import curve_metadata, curve_trade_roles, curve_trade_uses
from desk_pricing.curves import curve_convention
from desk_runtime.logging_config import get_logger
from market_data_service import curve_store
from market_data_service.config import (
    CURVE_FEED_LOOP_SLEEP_SECONDS,
    CURVE_REFETCH_SECONDS,
    CURVE_RETRY_SECONDS,
    SERVICE_NAME,
)
from market_data_service.publisher import publish_curve

log = get_logger(SERVICE_NAME)


def wire_curve(entry):
    """The published curve: percent points plus pricing arrays in years and decimal rates."""
    points = entry["points"]
    return {
        "provider": entry["provider"],
        "curve_name": entry["curve_name"],
        **curve_metadata(entry["curve_name"]),
        "curve_basis": entry["curve_basis"],
        "roles": list(curve_trade_roles(entry["curve_name"])),
        "uses": list(curve_trade_uses(entry["curve_name"])),
        "currency": entry["currency"],
        "index_tenor": entry["index_tenor"],
        "as_of_date": entry["as_of_date"],
        "received_at": entry["received_at"],
        "event_time": entry["received_at"],
        "points": points,
        "tenors": [float(point["tenor_years"]) for point in points],
        "rates": [float(point["rate"]) / 100.0 for point in points],
        **curve_convention(),
        **({"raw_payload": entry["raw_payload"]} if "raw_payload" in entry else {}),
    }


def _every(seconds):
    hours = round(seconds / 3600)
    if hours < 24:
        return f"every {hours} h"
    days = round(hours / 24)
    return "every day" if days == 1 else f"every {days} days"


@dataclass(frozen=True)
class CurveBuilder:
    curve_name: str
    build: Callable
    refetch_seconds: int = CURVE_REFETCH_SECONDS
    request_cost: int = 1


class CurveFeed:
    """Re-reads each curve of one provider on its own cadence and publishes stored revisions."""

    def __init__(self, provider, runtime, client, builders):
        self.provider = provider
        self.runtime = runtime
        self.client = client
        self.builders = {builder.curve_name: builder for builder in builders}
        self._next_due = {}
        self._last_as_of = {}

    def runtime_snapshot(self):
        return {
            **self.runtime.snapshot([]),
            "curves": self.curve_names(),
            "strategy": self.strategy(),
        }

    def _fetch_curve(self, builder):
        curve_set = builder.build(self.client)
        accepted, as_of = curve_store.store_curve_set(curve_set)
        if accepted:
            publish_curve(wire_curve(curve_store.curve_entry(curve_set, curve_set.points)))
        else:
            log.info(
                "older_curve_revision_ignored",
                provider=self.provider,
                curve=builder.curve_name,
                as_of_date=str(curve_set.as_of_date),
            )
        self._last_as_of[builder.curve_name] = as_of
        self.runtime.record_success()
        return as_of

    def _poll_tick(self):
        if self.runtime.cooldown_seconds_left() > 0:
            return
        for builder in self.builders.values():
            if self._next_due.get(builder.curve_name, 0) > time.monotonic():
                continue
            as_of = None
            if self.runtime.acquire(builder.request_cost, calls=builder.request_cost) is None:
                as_of, _ = self.runtime.guarded(
                    lambda: self._fetch_curve(builder), "curve_unavailable",
                    curve=builder.curve_name,
                )
            interval = builder.refetch_seconds if as_of is not None else CURVE_RETRY_SECONDS
            self._next_due[builder.curve_name] = time.monotonic() + interval

    def poll_loop(self):
        if not self.runtime.enabled:
            log.warning("curve_feed_disabled", provider=self.provider)
            return
        while True:
            try:
                self._poll_tick()
            except Exception:
                log.exception("curve_feed_tick_failed", provider=self.provider)
            time.sleep(CURVE_FEED_LOOP_SLEEP_SECONDS)

    def curve_names(self):
        return sorted(self.builders)

    def strategy(self):
        cadences = {
            name: builder.refetch_seconds for name, builder in sorted(self.builders.items())
        }
        intervals = sorted(set(cadences.values()))
        described = f"curves re-read {_every(intervals[0])}"
        if len(intervals) > 1:
            described += f", the slowest {_every(intervals[-1])}"
        return {
            "mode": "SCHEDULED_REFETCH",
            "curves": {
                name: str(self._last_as_of.get(name)) if name in self._last_as_of else None
                for name in sorted(self.builders)
            },
            "refetch_seconds": cadences,
            "retry_seconds": CURVE_RETRY_SECONDS,
            "next_curve_seconds": max(0, round(min(
                (due - time.monotonic() for due in self._next_due.values()), default=0
            ))),
            "description": described,
        }
