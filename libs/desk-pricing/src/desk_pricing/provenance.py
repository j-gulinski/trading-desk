"""Pricing provenance for curve-derived values."""

from desk_pricing.curves import curve_convention, rate_at


def pricing_provenance(model, curve=None, maturity_years=None):
    if not curve:
        return {"model": model}
    discount = {
        "name": curve.get("curve_name"),
        "provider": curve.get("provider"),
        "as_of_date": curve.get("as_of_date"),
        "received_at": curve.get("received_at"),
    }
    if maturity_years is not None:
        discount["maturity_rate_percent"] = rate_at(curve["tenors"], curve["rates"], float(maturity_years)) * 100
    return {"model": model, "curves": {"discount": discount}, **curve_convention()}
