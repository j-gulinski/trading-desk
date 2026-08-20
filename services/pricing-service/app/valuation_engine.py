import time
from decimal import Decimal

from app import cache
from app.pnl import compute_pnl, signed_quantity
from app.valuation_publisher import publish_valuation
from app.config import TRADE_REFRESH_SECONDS, SERVICE_NAME
from shared.config import DEFAULT_QUOTE_PROVIDER
from shared.term_schemas import DEFAULT_CURVE, DEFAULT_VOLATILITY
from shared.functions import first_present, get_iso_timestamp
from shared.pricing_math import bond_pv, european_option_pv, irs_pv
from shared.symbols import SPOT_ASSET_CLASSES
from shared.logging_config import get_logger

log = get_logger(SERVICE_NAME)


def market_inputs(asset_class, symbol, meta, provider=None):
    provider = provider or DEFAULT_QUOTE_PROVIDER
    inputs = {}
    if asset_class in SPOT_ASSET_CLASSES:
        inputs["spot"] = cache.get_spot(provider, symbol)
    elif asset_class == "EUROPEAN_OPTION":
        inputs["spot"] = cache.get_spot(provider, meta["underlying_symbol"])
        inputs["curve"] = cache.get_curve(meta.get("curve", DEFAULT_CURVE))
    elif asset_class in ("BOND", "IRS"):
        inputs["curve"] = cache.get_curve(meta.get("curve", DEFAULT_CURVE))
    return inputs


def price_from_inputs(asset_class, meta, inputs):
    spot = inputs.get("spot")
    curve = inputs.get("curve")

    if asset_class in SPOT_ASSET_CLASSES:
        if not spot:
            return None
        price = first_present(spot, ("mid", "last"))
        if price is None:
            return None
        return Decimal(str(price)), 1

    if asset_class == "BOND":
        if not curve:
            return None
        return Decimal(str(bond_pv(meta, curve))), 1

    if asset_class == "EUROPEAN_OPTION":
        if not spot or not curve:
            return None
        underlying = first_present(spot, ("mid", "last"))
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


def price_instrument(asset_class, symbol, meta, provider=None):
    return price_from_inputs(
        asset_class, meta, market_inputs(asset_class, symbol, meta, provider)
    )


def value_trade(trade):
    meta = trade.get("metadata") or {}
    inputs = market_inputs(
        trade["asset_class"], trade["symbol"], meta, cache.trade_provider(trade)
    )
    priced = price_from_inputs(trade["asset_class"], meta, inputs)
    if priced is None:
        return None
    price, multiplier = priced
    spot = inputs.get("spot") or {}
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
        "market_data_provider": spot.get("provider"),
        "market_data_timestamp": spot.get("provider_timestamp"),
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


def value_quote(provider, symbol):
    return _value_and_store(cache.trades_for_quote(provider, symbol))


def value_curve(curve_name):
    return _value_and_store(cache.trades_for_curve(curve_name))




def trade_refresh_loop():
    while True:
        try:
            for event in _value_and_store(cache.refresh_active_trades()):
                publish_valuation(event)
            for valuation in cache.finalize_closed_trades():
                cache.record_valuation(valuation)
                publish_valuation(valuation)
        except Exception:
            log.exception("refresh_failed")
        time.sleep(TRADE_REFRESH_SECONDS)
