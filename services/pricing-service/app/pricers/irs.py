"""IRS path: project floating cashflows, discount both legs, then net by direction."""

from decimal import Decimal

from app import cache
from app.pricers.common import discount_curve_name, finite_price, shock_curves
from app.pricers.contract import PricerRegistration
from shared.pricing.irs import irs_fair_fixed_rate, irs_legs, irs_pv


def load_inputs(_symbol, meta, _provider):
    inputs = {"curve": cache.get_curve(discount_curve_name(meta))}
    if meta.get("projection_curve"):
        inputs["projection_curve"] = cache.get_curve(meta["projection_curve"])
    return inputs


def _complete_inputs(meta, inputs):
    if not inputs.get("curve"):
        return False
    return not meta.get("projection_curve") or inputs.get("projection_curve") is not None


def calculate(meta, inputs):
    if not _complete_inputs(meta, inputs):
        return None
    return finite_price(
        irs_pv(meta, inputs["curve"], inputs.get("projection_curve"))
    )


def details(terms, inputs):
    if not _complete_inputs(terms, inputs):
        return {}
    legs = irs_legs(terms, inputs["curve"], inputs.get("projection_curve"))
    par_rate = irs_fair_fixed_rate(
        terms, inputs["curve"], inputs.get("projection_curve")
    )
    return {
        "fixed_leg_pv": Decimal(str(legs["fixed_leg_pv"])),
        "floating_leg_pv": Decimal(str(legs["floating_leg_pv"])),
        "par_rate": Decimal(str(par_rate)) if par_rate is not None else None,
    }


registration = PricerRegistration(
    asset_classes=("IRS",),
    load_inputs=load_inputs,
    calculate=calculate,
    shock_inputs=shock_curves,
    details=details,
)
