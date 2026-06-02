import time
import logging

from app import cache
from app.pnl import compute_pnl
from app.valuation_publisher import publish_valuation
from app.config import TRADE_REFRESH_SECONDS
from shared.functions import get_iso_timestamp


def rate_at(tenors, rates, t):
    if t <= tenors[0]:
        return rates[0]
    if t >= tenors[-1]:
        return rates[-1]
    for i in range(1, len(tenors)):
        if t <= tenors[i]:
            t0, t1, r0, r1 = tenors[i - 1], tenors[i], rates[i - 1], rates[i]
            return r0 + (r1 - r0) * (t - t0) / (t1 - t0)
    return rates[-1]


def _bond_pv(meta, curve):
    face = meta["face_value"]
    ppy = meta["payments_per_year"]
    periods = int(meta["maturity_years"] * ppy)
    coupon = face * meta["coupon_rate"] / ppy
    pv = 0.0
    for i in range(1, periods + 1):
        t = i / ppy
        r = rate_at(curve["tenors"], curve["rates"], t)
        cashflow = coupon + (face if i == periods else 0.0)
        pv += cashflow / (1 + r) ** t
    return pv


def _current_price_and_mult(trade):
    asset_class = trade["asset_class"]
    meta = trade.get("metadata") or {}

    if asset_class in ("EQUITY", "COMMODITY", "FUTURES"):
        spot = cache.get_spot(trade["symbol"])
        if not spot:
            return None, None
        price = spot.get("mid") or spot.get("last") or spot.get("spot")
        if price is None:
            return None, None
        multiplier = meta.get("multiplier", 1) if asset_class == "FUTURES" else 1
        return price, multiplier

    if asset_class == "FX":
        spot = cache.get_spot(trade["symbol"])
        if not spot or spot.get("spot") is None:
            return None, None
        s = spot["spot"]
        rd = spot.get("domestic_rate", 0.0)
        rf = spot.get("foreign_rate", 0.0)
        T = meta.get("tenor_years", 1.0)
        forward = s * (1 + rd * T) / (1 + rf * T)
        return forward, 1

    if asset_class == "BOND":
        curve = cache.get_curve(meta.get("curve", "USD_GOV"))
        if not curve:
            return None, None
        return _bond_pv(meta, curve), 1

    return None, None


def value_trade(trade):
    price, multiplier = _current_price_and_mult(trade)
    if price is None:
        return None
    quantity = trade["quantity"]
    fair_value = price * quantity * multiplier
    unrealized, realized, total = compute_pnl(
        trade["side"], price, trade["trade_price"], quantity, multiplier
    )
    return {
        "trade_id": trade["trade_id"],
        "book_id": trade["book_id"],
        "asset_class": trade["asset_class"],
        "symbol": trade["symbol"],
        "currency": trade["currency"],
        "fair_value": round(fair_value, 4),
        "market_value": round(fair_value, 4),
        "unrealized_pnl": round(unrealized, 4),
        "realized_pnl": round(realized, 4),
        "total_pnl": round(total, 4),
        "valuation_time": get_iso_timestamp(),
        "valuation_payload": {"current_price": round(price, 6), "multiplier": multiplier},
    }


def _value_and_store(trades):
    events = []
    for trade in trades:
        valuation = value_trade(trade)
        if valuation is None:
            continue
        cache.record_valuation(valuation)
        cache.save_valuation(valuation)
        events.append(valuation)
    return events


def value_symbol(symbol):
    return _value_and_store(cache.trades_for_symbol(symbol))


def value_curve(curve_name):
    return _value_and_store(cache.bond_trades())


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
            logging.exception("Trade refresh/finalize failed; retrying")
        time.sleep(TRADE_REFRESH_SECONDS)
