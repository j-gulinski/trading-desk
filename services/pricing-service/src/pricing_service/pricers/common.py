"""Small numerical and scenario helpers shared by asset implementations."""

from decimal import Decimal

SPOT_LEVEL_KEYS = ("spot", "mid", "last", "bid", "ask")


def finite_price(value, multiplier=1):
    try:
        price = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError):
        return None
    return (price, multiplier) if price.is_finite() else None


def discount_curve_name(meta):
    return meta.get("discount_curve") or meta.get("curve")


def shock_spot(inputs, shock):
    spot = inputs.get("spot")
    if not spot:
        return None
    factor = Decimal(str(1.0 + shock))
    return {
        **inputs,
        "spot": {
            key: value * factor
            if key in SPOT_LEVEL_KEYS and isinstance(value, Decimal)
            else value
            for key, value in spot.items()
        },
    }


def _bump_curve(curve, bump):
    return {**curve, "rates": [rate + bump for rate in curve["rates"]]}


def shock_curves(inputs, shock_bps):
    curve = inputs.get("curve")
    if not curve:
        return None
    bump = shock_bps / 10000.0
    shocked = {**inputs, "curve": _bump_curve(curve, bump)}
    projection = inputs.get("projection_curve")
    if projection:
        shocked["projection_curve"] = _bump_curve(projection, bump)
    return shocked
