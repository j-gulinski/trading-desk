from enum import Enum


class QuoteGrade(str, Enum):
    REALTIME = "REALTIME"
    EOD = "EOD"
    REFERENCE = "REFERENCE"


class FreshnessState(str, Enum):
    LIVE = "LIVE"
    STALE = "STALE"
    MISSING = "MISSING"
    UNSUPPORTED = "UNSUPPORTED"


def classify(supported, quote_timestamp, now, threshold_seconds):
    if not supported:
        return FreshnessState.UNSUPPORTED
    if quote_timestamp is None:
        return FreshnessState.MISSING
    age_seconds = (now - quote_timestamp).total_seconds()
    if age_seconds <= threshold_seconds:
        return FreshnessState.LIVE
    return FreshnessState.STALE
