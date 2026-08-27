from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, DecimalException

from shared.providers import ECB, EIOPA, FRED
from shared.quotes import as_decimal


@dataclass(frozen=True)
class CurvePoint:
    tenor_label: str
    tenor_years: Decimal
    rate: Decimal
    source_series: str | None
    source_as_of: date | None


DISCOUNT = "DISCOUNT"
PROJECTION = "PROJECTION"

GOVERNMENT_BONDS = "GOVERNMENT_BONDS"
INTEREST_RATE_SWAPS = "INTEREST_RATE_SWAPS"
OVERNIGHT_INDEX = "OVERNIGHT_INDEX"

EUR_RISK_FREE = "EUR_RISK_FREE"
USD_RISK_FREE = "USD_RISK_FREE"
PLN_RISK_FREE = "PLN_RISK_FREE"
EUR_GOVERNMENT_BONDS_AAA = "EUR_GOVERNMENT_BONDS_AAA"
EUR_GOVERNMENT_BONDS_ALL = "EUR_GOVERNMENT_BONDS_ALL"
USD_GOVERNMENT_BONDS = "USD_GOVERNMENT_BONDS"

CURVE_BASES = {
    GOVERNMENT_BONDS: (DISCOUNT, PROJECTION),
    INTEREST_RATE_SWAPS: (DISCOUNT, PROJECTION),
    OVERNIGHT_INDEX: (DISCOUNT, PROJECTION),
}

CURVE_CATALOG = {
    EUR_RISK_FREE: {
        "provider": EIOPA,
        "currency": "EUR",
        "family": "RISK_FREE",
        "display_name": "Risk-free",
        "display_qualifier": None,
        "stale_after_days": 75,
        "uses": (
            "BOND:DISCOUNT", "EUROPEAN_OPTION:DISCOUNT",
            "IRS:DISCOUNT", "IRS:PROJECTION",
        ),
    },
    USD_RISK_FREE: {
        "provider": EIOPA,
        "currency": "USD",
        "family": "RISK_FREE",
        "display_name": "Risk-free",
        "display_qualifier": None,
        "stale_after_days": 75,
        "uses": (
            "BOND:DISCOUNT", "EUROPEAN_OPTION:DISCOUNT",
            "IRS:DISCOUNT", "IRS:PROJECTION",
        ),
    },
    PLN_RISK_FREE: {
        "provider": EIOPA,
        "currency": "PLN",
        "family": "RISK_FREE",
        "display_name": "Risk-free",
        "display_qualifier": None,
        "stale_after_days": 75,
        "uses": (
            "BOND:DISCOUNT", "EUROPEAN_OPTION:DISCOUNT",
            "IRS:DISCOUNT", "IRS:PROJECTION",
        ),
    },
    EUR_GOVERNMENT_BONDS_AAA: {
        "provider": ECB,
        "currency": "EUR",
        "family": "GOVERNMENT_BONDS",
        "display_name": "Government bonds",
        "display_qualifier": "AAA",
        "stale_after_days": 7,
        "uses": ("BOND:DISCOUNT",),
    },
    EUR_GOVERNMENT_BONDS_ALL: {
        "provider": ECB,
        "currency": "EUR",
        "family": "GOVERNMENT_BONDS",
        "display_name": "Government bonds",
        "display_qualifier": "all ratings",
        "stale_after_days": 7,
        "uses": ("BOND:DISCOUNT",),
    },
    USD_GOVERNMENT_BONDS: {
        "provider": FRED,
        "currency": "USD",
        "family": "GOVERNMENT_BONDS",
        "display_name": "Government bonds",
        "display_qualifier": None,
        "stale_after_days": 7,
        "uses": ("BOND:DISCOUNT",),
    },
}


def curve_provider(curve_name):
    definition = CURVE_CATALOG.get(curve_name)
    return definition.get("provider") if definition else None


def curve_currency(curve_name):
    definition = CURVE_CATALOG.get(curve_name)
    return definition.get("currency") if definition else None


def curve_names_for_provider(provider):
    return tuple(
        curve_name
        for curve_name, definition in CURVE_CATALOG.items()
        if definition["provider"] == provider
    )


def curve_roles(curve_basis):
    return CURVE_BASES.get(curve_basis, ())


def curve_trade_uses(curve_name):
    return CURVE_CATALOG.get(curve_name, {}).get("uses", ())


def curve_trade_roles(curve_name):
    return tuple(sorted({use.rsplit(":", 1)[-1] for use in curve_trade_uses(curve_name)}))


def curve_metadata(curve_name):
    definition = CURVE_CATALOG.get(curve_name)
    if definition is None:
        return {
            "curve_family": None,
            "display_name": curve_name,
            "display_qualifier": None,
        }
    return {
        "curve_family": definition["family"],
        "display_name": definition["display_name"],
        "display_qualifier": definition["display_qualifier"],
    }


def curve_stale_after_days(curve_name):
    definition = CURVE_CATALOG.get(curve_name)
    return definition.get("stale_after_days") if definition else None


@dataclass(frozen=True)
class CurveSet:
    provider: str
    curve_name: str
    curve_basis: str
    currency: str
    index_tenor: str | None
    as_of_date: date
    received_at: datetime
    points: tuple
    raw_payload: dict


def build_curve_point(tenor_label, tenor_years, rate, source_series=None, source_as_of=None):
    try:
        years = as_decimal(tenor_years)
        rate_percent = as_decimal(rate)
    except (DecimalException, TypeError, ValueError) as error:
        raise ValueError(f"curve point {tenor_label} must be numeric") from error
    if not str(tenor_label or "").strip():
        raise ValueError("curve point tenor label is required")
    if years is None or not years.is_finite() or years <= 0:
        raise ValueError(f"curve point {tenor_label} tenor must be finite and positive")
    if rate_percent is None or not rate_percent.is_finite() or rate_percent <= -100:
        raise ValueError(
            f"curve point {tenor_label} rate must be finite and greater than -100%"
        )
    return CurvePoint(
        tenor_label=tenor_label,
        tenor_years=years,
        rate=rate_percent,
        source_series=source_series,
        source_as_of=source_as_of,
    )


def build_curve_set(provider, curve_name, curve_basis, currency, as_of_date, received_at,
                    points, raw_payload, index_tenor=None):
    definition = CURVE_CATALOG.get(curve_name)
    if definition is None:
        raise ValueError(f"curve {curve_name} is not in the curve catalog")
    if provider != definition["provider"]:
        raise ValueError(
            f"curve {curve_name} belongs to {definition['provider']}, not {provider}"
        )
    if currency != definition["currency"]:
        raise ValueError(
            f"curve {curve_name} is {definition['currency']}, not {currency}"
        )
    if len(points) < 2:
        raise ValueError(f"curve {curve_name} from {provider} needs at least two points")
    if curve_basis not in CURVE_BASES:
        raise ValueError(f"curve {curve_name} from {provider} has unknown basis {curve_basis}")
    labels = [point.tenor_label for point in points]
    if len(set(labels)) != len(labels):
        raise ValueError(f"curve {curve_name} from {provider} repeats a tenor")
    tenors = [point.tenor_years for point in points]
    if len(set(tenors)) != len(tenors):
        raise ValueError(f"curve {curve_name} from {provider} repeats a tenor year")
    return CurveSet(
        provider=provider,
        curve_name=curve_name,
        curve_basis=curve_basis,
        currency=currency,
        index_tenor=index_tenor,
        as_of_date=as_of_date,
        received_at=received_at,
        points=tuple(sorted(points, key=lambda point: point.tenor_years)),
        raw_payload=raw_payload,
    )
