"""Bond pricing path: contract cashflows discounted on one selected curve."""

from pricing_service import cache
from pricing_service.pricers.common import discount_curve_name, finite_price, shock_curves
from pricing_service.pricers.contract import PricerRegistration
from desk_pricing.bond import bond_pv


def load_inputs(_symbol, meta, _provider):
    return {"curve": cache.get_curve(discount_curve_name(meta))}


def calculate(meta, inputs):
    curve = inputs.get("curve")
    return None if not curve else finite_price(bond_pv(meta, curve))


registration = PricerRegistration(
    asset_classes=("BOND",),
    load_inputs=load_inputs,
    calculate=calculate,
    shock_inputs=shock_curves,
)
