from enum import Enum


class QuoteGrade(str, Enum):
    REALTIME = "REALTIME"
    EOD = "EOD"
    REFERENCE = "REFERENCE"


class FreshnessState(str, Enum):
    LIVE = "LIVE"
    STALE = "STALE"
    CLOSED = "CLOSED"
    MISSING = "MISSING"
    UNSUPPORTED = "UNSUPPORTED"


def classify(supported, provider_timestamp, received_at, now, stale_after_seconds,
             market_open=None, closed_stale_after_seconds=None):
    if not supported:
        return FreshnessState.UNSUPPORTED
    if provider_timestamp is None and received_at is None:
        return FreshnessState.MISSING
    if market_open is False and received_at is not None and closed_stale_after_seconds:
        received_age = (now - received_at).total_seconds()
        if received_age <= closed_stale_after_seconds:
            return FreshnessState.CLOSED
        return FreshnessState.STALE
    if provider_timestamp is None or not stale_after_seconds:
        return FreshnessState.MISSING
    age_seconds = (now - provider_timestamp).total_seconds()
    if age_seconds <= stale_after_seconds:
        return FreshnessState.LIVE
    return FreshnessState.STALE
