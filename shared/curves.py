from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from shared.quotes import as_decimal


@dataclass(frozen=True)
class CurvePoint:
    tenor_label: str
    tenor_years: Decimal
    rate: Decimal
    source_series: str | None
    source_as_of: date | None


CURVE_TYPES = ("GOV_ZERO", "COMPOSITE_REF", "POLICY_PROXY")


@dataclass(frozen=True)
class CurveSet:
    provider: str
    curve_name: str
    curve_type: str
    currency: str
    index_tenor: str | None
    as_of_date: date
    received_at: datetime
    points: tuple
    raw_payload: dict


def build_curve_point(tenor_label, tenor_years, rate, source_series=None, source_as_of=None):
    return CurvePoint(
        tenor_label=tenor_label,
        tenor_years=as_decimal(tenor_years),
        rate=as_decimal(rate),
        source_series=source_series,
        source_as_of=source_as_of,
    )


def build_curve_set(provider, curve_name, curve_type, currency, as_of_date, received_at,
                    points, raw_payload, index_tenor=None):
    if not points:
        raise ValueError(f"curve {curve_name} from {provider} has no points")
    if curve_type not in CURVE_TYPES:
        raise ValueError(f"curve {curve_name} from {provider} has unknown type {curve_type}")
    labels = [point.tenor_label for point in points]
    if len(set(labels)) != len(labels):
        raise ValueError(f"curve {curve_name} from {provider} repeats a tenor")
    return CurveSet(
        provider=provider,
        curve_name=curve_name,
        curve_type=curve_type,
        currency=currency,
        index_tenor=index_tenor,
        as_of_date=as_of_date,
        received_at=received_at,
        points=tuple(sorted(points, key=lambda point: point.tenor_years)),
        raw_payload=raw_payload,
    )
