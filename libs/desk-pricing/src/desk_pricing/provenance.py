"""Pricing provenance for curve-derived values."""

from desk_pricing.curves import curve_convention


MODEL_NAMES = {
    "BOND": "BOND_DCF",
    "EUROPEAN_OPTION": "BLACK_SCHOLES",
    "IRS": "IRS_SINGLE_CURVE",
}


def _curve_revision(curve):
    return {
        "name": curve.get("curve_name"),
        "provider": curve.get("provider"),
        "as_of_date": curve.get("as_of_date"),
        "received_at": curve.get("received_at"),
    }


def pricing_provenance(asset_class, discount_curve, projection_curve=None):
    model = MODEL_NAMES.get(asset_class)
    if model is None or not discount_curve:
        return None
    curves = {"discount": _curve_revision(discount_curve)}
    if projection_curve:
        curves["projection"] = _curve_revision(projection_curve)
    return {
        "model": model,
        "curves": curves,
        **curve_convention(),
    }
