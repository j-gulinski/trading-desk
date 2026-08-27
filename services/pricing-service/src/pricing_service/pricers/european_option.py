"""European option path: underlying quote plus a matching discount curve."""

from pricing_service import cache
from pricing_service.pricers.common import discount_curve_name, finite_price, shock_spot
from pricing_service.pricers.contract import PricerRegistration
from desk_runtime.config import DEFAULT_QUOTE_PROVIDER
from desk_runtime.functions import first_present
from desk_pricing.european_option import european_option_pv
from desk_domain.term_schemas import DEFAULT_VOLATILITY


def load_inputs(_symbol, meta, provider):
    return {
        "spot": cache.get_spot(
            provider or DEFAULT_QUOTE_PROVIDER, meta["underlying_symbol"]
        ),
        "curve": cache.get_curve(discount_curve_name(meta)),
    }


def calculate(meta, inputs):
    spot = inputs.get("spot")
    curve = inputs.get("curve")
    if not spot or not curve:
        return None
    underlying = first_present(spot, ("mid", "last"))
    if underlying is None:
        return None
    price = european_option_pv(
        meta,
        underlying,
        curve,
        meta.get("volatility", DEFAULT_VOLATILITY),
    )
    return finite_price(price, int(meta.get("multiplier", 1)))


registration = PricerRegistration(
    asset_classes=("EUROPEAN_OPTION",),
    load_inputs=load_inputs,
    calculate=calculate,
    shock_inputs=shock_spot,
)
