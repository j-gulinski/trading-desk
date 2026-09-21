"""Shape of the valuation record that pricing publishes and the blotter caches."""

import datetime

from desk_domain.quotes import as_decimal

NUMERIC_FIELDS = (
    "fair_value",
    "market_value",
    "unrealized_pnl",
    "realized_pnl",
    "total_pnl",
)


def valued_at(valuation):
    try:
        return datetime.datetime.fromisoformat(str(valuation.get("valuation_time")))
    except (TypeError, ValueError):
        return None


def is_final(valuation):
    return bool((valuation.get("valuation_payload") or {}).get("final"))


def with_decimals(valuation):
    return {
        **valuation,
        **{
            field: as_decimal(valuation[field])
            for field in NUMERIC_FIELDS
            if valuation.get(field) is not None
        },
    }
