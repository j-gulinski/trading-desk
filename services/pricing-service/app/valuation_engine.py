import time
from decimal import Decimal

from app import cache
from app.pnl import compute_pnl, signed_quantity
from app.valuation_publisher import publish_valuation
from app.config import TRADE_REFRESH_SECONDS, SERVICE_NAME
from shared.catalog import DEFAULT_CURVE, DEFAULT_VOLATILITY
from shared.functions import first_present, get_iso_timestamp
from shared.pricing_math import (
    bond_pv,
    european_option_pv,
    fx_forward,
    irs_pv,
)
from shared.logging_config import get_logger

log = get_logger(SERVICE_NAME)


def market_inputs(asset_class, symbol, meta):
    inputs = {}
    if asset_class in ("EQUITY", "COMMODITY", "FUTURES", "FX"):
        inputs["spot"] = cache.get_spot(symbol)
    elif asset_class == "EUROPEAN_OPTION":
        inputs["spot"] = cache.get_spot(meta["underlying_symbol"])
        inputs["curve"] = cache.get_curve(meta.get("curve", DEFAULT_CURVE))
    elif asset_class in ("BOND", "IRS"):
        inputs["curve"] = cache.get_curve(meta.get("curve", DEFAULT_CURVE))
    return inputs


def price_from_inputs(asset_class, meta, inputs):
    spot = inputs.get("spot")
    curve = inputs.get("curve")

    if asset_class in ("EQUITY", "COMMODITY", "FUTURES"):
        if not spot:
            return None
        price = first_present(spot, ("mid", "last", "spot"))
        if price is None:
            return None
        multiplier = int(meta.get("multiplier", 1)) if asset_class == "FUTURES" else 1
        return Decimal(str(price)), multiplier

    if asset_class == "FX":
        if not spot or spot.get("spot") is None:
            return None
        s = Decimal(str(spot["spot"]))
        rd = Decimal(str(spot.get("domestic_rate", 0.0)))
        rf = Decimal(str(spot.get("foreign_rate", 0.0)))
        T = Decimal(str(meta.get("tenor_years", 1.0)))
        return fx_forward(s, rd, rf, T), 1

    if asset_class == "BOND":
        if not curve:
            return None
        return Decimal(str(bond_pv(meta, curve))), 1

    if asset_class == "EUROPEAN_OPTION":
        if not spot or not curve:
            return None
        underlying = first_present(spot, ("mid", "last", "spot"))
        if underlying is None:
            return None
        volatility = meta.get("volatility", DEFAULT_VOLATILITY)
        price = european_option_pv(meta, underlying, curve, volatility)
        return Decimal(str(price)), int(meta.get("multiplier", 1))

    if asset_class == "IRS":
        if not curve:
            return None
        return Decimal(str(irs_pv(meta, curve))), 1

    return None


def price_instrument(asset_class, symbol, meta):
    return price_from_inputs(asset_class, meta, market_inputs(asset_class, symbol, meta))


def _current_price_and_mult(trade):
    return price_instrument(
        trade["asset_class"], trade["symbol"], trade.get("metadata") or {}
    )


def value_trade(trade):
    priced = _current_price_and_mult(trade)
    if priced is None:
        return None
    price, multiplier = priced
    quantity = trade["quantity"]
    fair_value = price * quantity * multiplier
    unrealized, realized, total = compute_pnl(
        trade["side"], price, trade["trade_price"], quantity, multiplier
    )
    return {
        "trade_id": trade["trade_id"],
        "book_id": trade["book_id"],
        "book_name": trade["book_name"],
        "asset_class": trade["asset_class"],
        "symbol": trade["symbol"],
        "currency": trade["currency"],
        "quantity": signed_quantity(trade["side"], quantity),
        "trade_price": trade["trade_price"],
        "fair_value": fair_value,
        "market_value": fair_value,
        "unrealized_pnl": unrealized,
        "realized_pnl": realized,
        "total_pnl": total,
        "valuation_time": get_iso_timestamp(),
        "valuation_payload": {"current_price": str(price), "multiplier": multiplier},
    }


def _value_and_store(trades):
    events = []
    for trade in trades:
        valuation = value_trade(trade)
        if valuation is None:
            continue
        if not cache.record_valuation(valuation):
            log.debug("valuation_after_final_dropped", trade_id=valuation["trade_id"])
            continue
        log.debug("valuation_computed", trade_id=valuation["trade_id"],
                  symbol=valuation["symbol"])
        cache.save_valuation(valuation)
        events.append(valuation)
    return events


def value_symbol(symbol):
    return _value_and_store(cache.trades_for_symbol(symbol))


def value_curve(curve_name):
    return _value_and_store(cache.trades_for_curve(curve_name))




def trade_refresh_loop():
    """Periodically re-query the active-trade set and finalize realized PnL for
    trades that have just been CLOSED"""
    while True:
        try:
            cache.refresh_active_trades()
            for valuation in cache.finalize_closed_trades():
                cache.record_valuation(valuation)
                publish_valuation(valuation)
        except Exception:
            log.exception("refresh_failed")
        time.sleep(TRADE_REFRESH_SECONDS)
