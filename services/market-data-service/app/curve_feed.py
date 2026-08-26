import threading
import time

from shared.curves import curve_metadata, curve_trade_roles, curve_trade_uses
from shared.logging_config import get_logger
from app import curve_store
from app.config import (
    CURVE_FEED_LOOP_SLEEP_SECONDS,
    CURVE_REFETCH_SECONDS,
    CURVE_RETRY_SECONDS,
    SERVICE_NAME,
)
from app.publisher import publish_curve
from app.quote_audit import audit_curve_set

log = get_logger(SERVICE_NAME)
PACING_ERROR = "provider request budget is temporarily exhausted"


def wire_points(points):
    return [
        {
            "tenor_label": point["tenor_label"],
            "tenor_years": point["tenor_years"],
            "rate": point["rate"],
            "source_series": point["source_series"],
            "source_as_of": point["source_as_of"],
        }
        for point in points
    ]


def wire_curve(entry):
    """Points keep published percent rates; tenors/rates are the pricing arrays
    (floats, decimal fractions)."""
    points = wire_points(entry["points"])
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
        **({"raw_payload": entry["raw_payload"]} if "raw_payload" in entry else {}),
    }


def curve_set_entry(curve_set):
    return {
        "provider": curve_set.provider,
        "curve_name": curve_set.curve_name,
        "curve_basis": curve_set.curve_basis,
        "currency": curve_set.currency,
        "index_tenor": curve_set.index_tenor,
        "as_of_date": curve_set.as_of_date,
        "received_at": curve_set.received_at,
        "points": [
            {
                "tenor_label": point.tenor_label,
                "tenor_years": point.tenor_years,
                "rate": point.rate,
                "source_series": point.source_series,
                "source_as_of": point.source_as_of,
            }
            for point in curve_set.points
        ],
    }


def _every(seconds):
    hours = round(seconds / 3600)
    if hours < 24:
        return f"every {hours} h"
    days = round(hours / 24)
    return "every day" if days == 1 else f"every {days} days"


class CurveBuilder:
    def __init__(
        self,
        curve_name,
        build,
        refetch_seconds=CURVE_REFETCH_SECONDS,
        request_cost=1,
    ):
        self.curve_name = curve_name
        self.build = build
        self.refetch_seconds = refetch_seconds
        # Reserve the builder's worst-case provider calls before starting it.
        self.request_cost = request_cost


class CurveFeed:

    def __init__(self, provider, runtime, client, builders, enabled=True):
        self.provider = provider
        self.runtime = runtime
        self.client = client
        self.builders = {builder.curve_name: builder for builder in builders}
        self.enabled = enabled
        self._next_due = {}
        self._last_as_of = {}
        self._publish_locks = {
            builder.curve_name: threading.Lock() for builder in builders
        }

    def _disabled_reason(self):
        return None if self.enabled else f"{self.provider} is disabled: no API key configured"

    def runtime_snapshot(self):
        return {
            **self.runtime.snapshot([]),
            "curves": self.curve_names(),
            "strategy": self.strategy(),
        }

    def _fetch_curve(self, builder):
        curve_set = builder.build(self.client, self.runtime.record_request)
        with self._publish_locks[builder.curve_name]:
            created, changed, accepted = curve_store.store_curve_set(curve_set)
            if not accepted:
                current = curve_store.latest_curve_set(
                    self.provider, builder.curve_name
                )
                if current is None:
                    raise RuntimeError(
                        f"{builder.curve_name} rejected without a stored revision"
                    )
                log.info(
                    "older_curve_revision_ignored",
                    provider=self.provider,
                    curve=builder.curve_name,
                    as_of_date=str(curve_set.as_of_date),
                )
                entry = current
            else:
                if created or changed:
                    audit_curve_set(curve_set, created)
                entry = curve_set_entry(curve_set)
                publish_curve(wire_curve(entry))
        self._last_as_of[builder.curve_name] = entry["as_of_date"]
        self.runtime.record_success()
        return entry

    def _guarded_fetch(self, builder):
        if not self.runtime.try_take(builder.request_cost):
            return None, PACING_ERROR
        try:
            return self.runtime.guarded(
                lambda: self._fetch_curve(builder), "curve_unavailable",
                curve=builder.curve_name,
            )
        except Exception:
            log.exception(
                "curve_build_failed",
                provider=self.provider,
                curve=builder.curve_name,
            )
            return None, f"{builder.curve_name} could not be built from the provider response"

    def _schedule_next(self, builder, succeeded):
        interval = builder.refetch_seconds if succeeded else CURVE_RETRY_SECONDS
        self._next_due[builder.curve_name] = time.monotonic() + interval

    def _poll_tick(self):
        if self.runtime.cooldown_seconds_left() > 0:
            return
        for builder in self.builders.values():
            if self._next_due.get(builder.curve_name, 0) <= time.monotonic():
                entry, _ = self._guarded_fetch(builder)
                self._schedule_next(builder, entry is not None)

    def poll_loop(self):
        if not self.enabled:
            log.warning("curve_feed_disabled", provider=self.provider)
            return
        while True:
            try:
                self._poll_tick()
            except Exception:
                log.exception("curve_feed_tick_failed", provider=self.provider)
            time.sleep(CURVE_FEED_LOOP_SLEEP_SECONDS)

    def refresh_curve(self, curve_name):
        """Returns (entry, error, http_status)."""
        builder = self.builders.get(curve_name)
        if builder is None:
            return None, f"{self.provider} does not build {curve_name}", 404
        unavailable = self._disabled_reason() or self.runtime.unavailable()
        if unavailable is not None:
            return None, unavailable, 503
        entry, error = self._guarded_fetch(builder)
        self._schedule_next(builder, entry is not None)
        if entry is None:
            http_status = (
                429
                if error == PACING_ERROR or self.runtime.status() == "RATE_LIMITED"
                else 502
            )
            return None, error, http_status
        return entry, None, 200

    def refresh_all(self):
        refreshed, skipped = [], []
        for curve_name in sorted(self.builders):
            entry, error, _ = self.refresh_curve(curve_name)
            if error is None:
                refreshed.append({"provider": self.provider, "curve": curve_name,
                                  "as_of_date": entry["as_of_date"]})
            else:
                skipped.append({"provider": self.provider, "curve": curve_name,
                                "reason": error})
        return refreshed, skipped

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
