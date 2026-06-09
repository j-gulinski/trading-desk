import time
from decimal import Decimal

from app import cache
from app.pnl import compute_pnl
from app.valuation_publisher import publish_valuation
from app.config import TRADE_REFRESH_SECONDS, SERVICE_NAME
from shared.functions import get_iso_timestamp
from shared.pricing_math import bond_pv
from shared.logging_config import get_logger

log = get_logger(SERVICE_NAME)


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
        multiplier = int(meta.get("multiplier", 1)) if asset_class == "FUTURES" else 1
        return Decimal(str(price)), multiplier

    if asset_class == "FX":
        spot = cache.get_spot(trade["symbol"])
        if not spot or spot.get("spot") is None:
            return None, None
        s = spot["spot"]
        rd = spot.get("domestic_rate", 0.0)
        rf = spot.get("foreign_rate", 0.0)
        T = meta.get("tenor_years", 1.0)
        forward = s * (1 + rd * T) / (1 + rf * T)
        return Decimal(str(forward)), 1

    if asset_class == "BOND":
        curve = cache.get_curve(meta.get("curve", "USD_GOV"))
        if not curve:
            return None, None
        return Decimal(str(bond_pv(meta, curve))), 1

    return None, None


def value_trade(trade):
    price, multiplier = _current_price_and_mult(trade)
    if price is None:
        return None
    quantity = trade["quantity"]  # Decimal
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
            log.exception("refresh_failed")
        time.sleep(TRADE_REFRESH_SECONDS)
