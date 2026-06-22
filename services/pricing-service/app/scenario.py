from decimal import Decimal

from app import cache
from app.pnl import compute_pnl
from app.schemas import ScenarioRequest
from shared.pricing_math import bond_pv


def _shocked_bond_pv(meta: dict, curve: dict, shock_bps: float) -> float:
    bump = shock_bps / 10000.0
    bumped = {"tenors": curve["tenors"], "rates": [r + bump for r in curve["rates"]]}
    return bond_pv(meta, bumped)


def _base_price_from_cache(inst) -> Decimal | None:
    if inst.asset_class in ("EQUITY", "COMMODITY", "FUTURES"):
        spot = cache.get_spot(inst.symbol)
        if not spot:
            return None
        raw = spot.get("spot") or spot.get("mid") or spot.get("last")
        return Decimal(str(raw)) if raw is not None else None

    if inst.asset_class == "FX":
        spot = cache.get_spot(inst.symbol)
        if not spot or spot.get("spot") is None:
            return None
        s = Decimal(str(spot["spot"]))
        rd = Decimal(str(spot.get("domestic_rate", 0.0)))
        rf = Decimal(str(spot.get("foreign_rate", 0.0)))
        T = Decimal(str(inst.meta.get("tenor_years", 1.0)))
        return s * (1 + rd * T) / (1 + rf * T)

    if inst.asset_class == "BOND":
        curve = cache.get_curve(inst.meta.get("curve", "USD_GOV"))
        if not curve:
            return None
        return Decimal(str(bond_pv(inst.meta, curve)))

    return None


def run_scenario(req: ScenarioRequest) -> dict | None:
    """
    Return base vs shocked valuation for an ad-hoc position.

    Shock convention (determined by asset_class):
      EQUITY / COMMODITY / FUTURES / FX  — decimal percentage (0.10 = +10% spot)
      BOND                                — basis points       (25   = +25 bps on curve)

    base_price in the request takes precedence over the cache. If omitted the
    current market price is fetched from the pricing service cache, which
    requires the market data stack to be running.
    """
    inst = req.position.instrument
    pos = req.position

    base_price = inst.current_price if inst.current_price is not None else _base_price_from_cache(inst)
    if base_price is None:
        return None

    if inst.asset_class in ("EQUITY", "COMMODITY", "FUTURES"):
        multiplier = int(inst.meta.get("multiplier", 1)) if inst.asset_class == "FUTURES" else 1
        shocked_price = base_price * Decimal(str(1 + req.shock))

    elif inst.asset_class == "FX":
        multiplier = 1
        shocked_price = base_price * Decimal(str(1 + req.shock))

    elif inst.asset_class == "BOND":
        multiplier = 1
        curve = cache.get_curve(inst.meta.get("curve", "USD_GOV"))
        if not curve:
            return None
        shocked_price = Decimal(str(_shocked_bond_pv(inst.meta, curve, req.shock)))

    else:
        return None

    base_fv = base_price * pos.quantity * multiplier
    shocked_fv = shocked_price * pos.quantity * multiplier
    base_unreal, _, _ = compute_pnl(pos.side, base_price, pos.trade_price, pos.quantity, multiplier)
    shocked_unreal, _, _ = compute_pnl(pos.side, shocked_price, pos.trade_price, pos.quantity, multiplier)

    return {
        "asset_class": inst.asset_class,
        "symbol": inst.symbol,
        "shock": req.shock,
        "base": {
            "price": base_price,
            "fair_value": base_fv,
            "unrealized_pnl": base_unreal,
        },
        "shocked": {
            "price": shocked_price,
            "fair_value": shocked_fv,
        },
        "unrealized_pnl": base_unreal,
        "scenario_pnl": shocked_unreal,
        "pnl_impact": shocked_unreal - base_unreal,
    }
