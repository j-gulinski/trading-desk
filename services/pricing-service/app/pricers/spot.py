"""Pricing path for directly quoted EQUITY, FX and COMMODITY instruments."""

from app import cache
from app.pricers.common import finite_price, shock_spot
from app.pricers.contract import PricerRegistration
from shared.config import DEFAULT_QUOTE_PROVIDER
from shared.functions import first_present
from shared.symbols import SPOT_ASSET_CLASSES


def load_inputs(symbol, _meta, provider):
    return {"spot": cache.get_spot(provider or DEFAULT_QUOTE_PROVIDER, symbol)}


def calculate(_meta, inputs):
    spot = inputs.get("spot")
    if not spot:
        return None
    price = first_present(spot, ("mid", "last"))
    return None if price is None else finite_price(price)


registration = PricerRegistration(
    asset_classes=tuple(SPOT_ASSET_CLASSES),
    load_inputs=load_inputs,
    calculate=calculate,
    shock_inputs=shock_spot,
)
