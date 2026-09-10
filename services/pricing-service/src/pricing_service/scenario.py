from desk_pricing.valuation import pnl, position_value
from pricing_service.market_inputs import market_inputs, shock_inputs
from pricing_service.schemas import ScenarioRequest


def run_scenario(req: ScenarioRequest) -> dict | None:
    instrument = req.instrument
    inputs = market_inputs(instrument, req.market_data_provider)
    base_priced = instrument.price(inputs)
    if base_priced is None:
        return None
    model_base, multiplier = base_priced["price"], base_priced["multiplier"]

    shocked = shock_inputs(instrument, inputs, req.shock)
    if shocked is None:
        return None
    shocked_priced = instrument.price(shocked)
    if shocked_priced is None:
        return None
    model_shocked = shocked_priced["price"]

    base_price = req.current_price if req.current_price is not None else model_base
    shocked_price = base_price + (model_shocked - model_base)

    entry_value = position_value(req.trade_price, req.quantity, multiplier)
    base_value = position_value(base_price, req.quantity, multiplier)
    scenario_value = position_value(shocked_price, req.quantity, multiplier)

    base_pnl = pnl(req.side, base_price, req.trade_price, req.quantity, multiplier)
    scenario_pnl = pnl(req.side, shocked_price, base_price, req.quantity, multiplier)
    current_pnl = base_pnl + scenario_pnl

    return {
        "asset_class": instrument.asset_class,
        "symbol": instrument.symbol,
        "side": req.side,
        "open_value": entry_value,
        "shock": req.shock,
        "base": {"price": base_price, "value": base_value, "base_pnl": base_pnl},
        "scenario": {"price": shocked_price, "value": scenario_value, "scenario_pnl": scenario_pnl},
        "base_pnl": base_pnl,
        "scenario_pnl": scenario_pnl,
        "current_pnl": current_pnl,
    }
