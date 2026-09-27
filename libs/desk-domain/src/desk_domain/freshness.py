from datetime import timedelta
from enum import Enum


class QuoteGrade(str, Enum):
    REALTIME = "REALTIME"
    EOD = "EOD"
    REFERENCE = "REFERENCE"


class FreshnessState(str, Enum):
    LIVE = "LIVE"
    STALE = "STALE"
    CLOSED = "CLOSED"
    EOD = "EOD"
    MISSING = "MISSING"


def assess(provider_timestamp, received_at, stale_after_seconds, market_open=None,
           closed_stale_after_seconds=None, grade=None):
    """The state a quote has while fresh and the moment it turns STALE (None if never usable)."""
    if grade == QuoteGrade.EOD:
        if provider_timestamp is None or not stale_after_seconds:
            return FreshnessState.MISSING, None
        return FreshnessState.EOD, provider_timestamp + timedelta(seconds=stale_after_seconds)
    if market_open is False and received_at is not None and closed_stale_after_seconds:
        return FreshnessState.CLOSED, received_at + timedelta(seconds=closed_stale_after_seconds)
    if provider_timestamp is None or not stale_after_seconds:
        return FreshnessState.MISSING, None
    return FreshnessState.LIVE, provider_timestamp + timedelta(seconds=stale_after_seconds)


def classify(provider_timestamp, received_at, now, stale_after_seconds, market_open=None,
             closed_stale_after_seconds=None, grade=None):
    state, stale_at = assess(provider_timestamp, received_at, stale_after_seconds, market_open,
                             closed_stale_after_seconds, grade)
    return state if stale_at is None or now <= stale_at else FreshnessState.STALE
