from decimal import Decimal

from desk_domain.instruments import FinancialInstrument

from desk_runtime.config import DEFAULT_QUOTE_PROVIDER
from pricing_service import cache


def market_inputs(instrument: FinancialInstrument, provider=None):
    terms = instrument.terms
    with cache.data_lock:
        inputs = {}
        if instrument.needs_quote:
            inputs["spot"] = cache.spots.get((provider or DEFAULT_QUOTE_PROVIDER, instrument.quote_symbol))
        if instrument.needs_curve:
            inputs["curve"] = cache.curves.get(terms.get("discount_curve"))
        if terms.get("projection_curve"):
            inputs["projection_curve"] = inputs.get("curve")
        return inputs


def shock_inputs(instrument: FinancialInstrument, inputs, shock):
    if instrument.needs_quote:
        spot = inputs.get("spot")
        if not spot:
            return None
        factor = Decimal(1) + Decimal(str(shock))
        return {**inputs, "spot": {**spot, **{
            key: Decimal(str(spot[key])) * factor
            for key in ("mid", "last", "bid", "ask") if spot.get(key) is not None
        }}}
    curve = inputs.get("curve")
    if not curve:
        return None
    bumped = {**curve, "rates": [rate + shock / 10000 for rate in curve["rates"]]}
    return {**inputs, "curve": bumped,
            **({"projection_curve": bumped} if "projection_curve" in inputs else {})}
