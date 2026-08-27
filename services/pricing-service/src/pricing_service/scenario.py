from decimal import Decimal

from pricing_service.pricers.registry import market_inputs, price_from_inputs, shock_inputs
from pricing_service.schemas import ScenarioRequest


def run_scenario(req: ScenarioRequest) -> dict | None:
    inst = req.position.instrument
    pos = req.position

    inputs = market_inputs(inst.asset_class, inst.symbol, inst.meta,
                           req.market_data_provider)
    base_priced = price_from_inputs(inst.asset_class, inst.meta, inputs)
    if base_priced is None:
        return None
    model_base, multiplier = base_priced

    shocked = shock_inputs(inst.asset_class, inputs, req.shock)
    if shocked is None:
        return None
    shocked_priced = price_from_inputs(inst.asset_class, inst.meta, shocked)
    if shocked_priced is None:
        return None
    model_shocked, _ = shocked_priced

    base_price = inst.current_price if inst.current_price is not None else model_base
    shocked_price = base_price + (model_shocked - model_base)

    direction = Decimal(-1) if pos.side == "SELL" else Decimal(1)

    entry_value = pos.trade_price * pos.quantity * multiplier
    base_value = base_price * pos.quantity * multiplier
    scenario_value = shocked_price * pos.quantity * multiplier

    base_pnl = (base_value - entry_value) * direction
    scenario_pnl = (scenario_value - base_value) * direction
    current_pnl = base_pnl + scenario_pnl

    return {
        "asset_class": inst.asset_class,
        "symbol": inst.symbol,
        "side": pos.side,
        "open_value": entry_value,
        "shock": req.shock,
        "base": {"price": base_price, "value": base_value, "base_pnl": base_pnl},
        "scenario": {"price": shocked_price, "value": scenario_value, "scenario_pnl": scenario_pnl},
        "base_pnl": base_pnl,
        "scenario_pnl": scenario_pnl,
        "current_pnl": current_pnl,
    }
