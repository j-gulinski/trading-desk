import time

from shared.functions import utcnow
from shared.logging_config import get_logger
from app import persistence
from app.clients.base import (
    ProviderDataError,
    ProviderError,
    ProviderRateLimited,
)
from app.config import (
    RATE_LIMIT_DEFAULT_COOLDOWN_SECONDS,
    REFERENCE_CONFIRM_SECONDS,
    REFERENCE_LOOP_SLEEP_SECONDS,
    REFERENCE_WINDOW_RETRY_SECONDS,
    SERVICE_NAME,
    TRANSIENT_ERROR_BACKOFF_SECONDS,
)
from app.publisher import publish_curve
from app.quote_audit import audit_curve_set

log = get_logger(SERVICE_NAME)


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
        "curve_type": entry["curve_type"],
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
        "curve_type": curve_set.curve_type,
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


class CurveBuilder:
    def __init__(self, curve_name, build, min_refetch_seconds=None, local=False):
        # local: assembled without provider HTTP — success says nothing about the source
        self.curve_name = curve_name
        self.build = build
        self.min_refetch_seconds = min_refetch_seconds
        self.local = local


class CurveFeed:
    def __init__(self, provider, runtime, calendar, client, builders):
        self.provider = provider
        self.runtime = runtime
        self.calendar = calendar
        self.client = client
        self.builders = {builder.curve_name: builder for builder in builders}
        self._next_due = {}
        self._latest_as_of = {}

    def _fetch_curve(self, builder):
        curve_set = builder.build(self.client, self.runtime.record_request)
        created, changed = persistence.store_curve_set(curve_set)
        if created or changed:
            audit_curve_set(curve_set, created)
        publish_curve(wire_curve(curve_set_entry(curve_set)))
        previous = self._latest_as_of.get(builder.curve_name)
        if previous is None or curve_set.as_of_date > previous:
            self._latest_as_of[builder.curve_name] = curve_set.as_of_date
        if not builder.local:
            self.runtime.record_success()
        return curve_set

    def _guarded_fetch(self, builder):
        try:
            return self._fetch_curve(builder), None
        except ProviderRateLimited as error:
            cooldown = error.retry_after_seconds or RATE_LIMIT_DEFAULT_COOLDOWN_SECONDS
            self.runtime.enter_cooldown(
                "RATE_LIMITED", "rate limited", error.detail, cooldown,
                "PROVIDER_RATE_LIMITED", "WARNING",
            )
            return None, f"{self.provider} is rate limited"
        except ProviderDataError as error:
            log.info("curve_unavailable", provider=self.provider,
                     curve=builder.curve_name, detail=error.detail)
            return None, error.detail
        except ProviderError as error:
            self.runtime.transient_error(error.detail, TRANSIENT_ERROR_BACKOFF_SECONDS)
            return None, error.detail

    def _schedule_next(self, builder, succeeded):
        now = utcnow()
        interval = REFERENCE_CONFIRM_SECONDS
        if succeeded and builder.min_refetch_seconds is not None:
            interval = builder.min_refetch_seconds
        else:
            awaiting = self._latest_as_of.get(builder.curve_name) is None or (
                self._latest_as_of[builder.curve_name] < self.calendar.source_today(now)
            )
            if self.calendar.in_window(now) and awaiting:
                interval = REFERENCE_WINDOW_RETRY_SECONDS
        self._next_due[builder.curve_name] = time.monotonic() + interval

    def _poll_tick(self):
        if self.runtime.cooldown_seconds_left() > 0:
            return
        for builder in self.builders.values():
            if self._next_due.get(builder.curve_name, 0) <= time.monotonic():
                curve_set, _ = self._guarded_fetch(builder)
                self._schedule_next(builder, curve_set is not None)

    def poll_loop(self):
        while True:
            try:
                self._poll_tick()
            except Exception:
                log.exception("curve_feed_tick_failed", provider=self.provider)
            time.sleep(REFERENCE_LOOP_SLEEP_SECONDS)

    def refresh_curve(self, curve_name):
        """Returns (entry, error, http_status)."""
        builder = self.builders.get(curve_name)
        if builder is None:
            return None, f"{self.provider} does not build {curve_name}", 404
        cooldown_left = self.runtime.cooldown_seconds_left()
        if cooldown_left > 0:
            return None, (
                f"{self.provider} is {self.runtime.status()}: "
                f"retry in {round(cooldown_left)}s"
            ), 503
        curve_set, error = self._guarded_fetch(builder)
        self._schedule_next(builder, curve_set is not None)
        if curve_set is None:
            http_status = 429 if self.runtime.status() == "RATE_LIMITED" else 502
            return None, error, http_status
        return curve_set_entry(curve_set), None, 200

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
        now = utcnow()
        window = self.calendar.describe_window()
        return {
            "mode": "PUBLICATION_CALENDAR",
            "window": window,
            "next_window_seconds": self.calendar.next_window_seconds(now),
            "curves": {
                name: str(self._latest_as_of[name]) if name in self._latest_as_of else None
                for name in sorted(self.builders)
            },
            "window_retry_seconds": REFERENCE_WINDOW_RETRY_SECONDS,
            "confirm_seconds": REFERENCE_CONFIRM_SECONDS,
            "description": f"curves {window} · hourly confirmation",
        }
