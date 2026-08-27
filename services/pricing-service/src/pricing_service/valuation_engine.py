"""Pricing, revaluation routing, and the active-trade polling loop."""

import time
import threading

from pricing_service import cache, repository
from pricing_service.pnl import compute_pnl, signed_quantity
from pricing_service.pricers.registry import market_inputs, price_from_inputs
from pricing_service.valuation_publisher import publish_valuation
from pricing_service.config import TRADE_REFRESH_SECONDS, SERVICE_NAME
from desk_runtime.functions import get_iso_timestamp
from desk_runtime.logging_config import get_logger
from desk_domain.audit import write_audit

log = get_logger(SERVICE_NAME)
_blocked_lock = threading.Lock()
_blocked_trades = set()


def _audit_blocked(trade):
    trade_id = trade["trade_id"]
    with _blocked_lock:
        if trade_id in _blocked_trades:
            return
        _blocked_trades.add(trade_id)
    write_audit(
        SERVICE_NAME,
        "VALUATION_BLOCKED",
        "Valuation blocked: required market data is unavailable",
        entity_type="TRADE",
        entity_id=trade_id,
        severity="WARNING",
        payload={
            "asset_class": trade["asset_class"],
            "symbol": trade["symbol"],
            "market_data_provider": trade.get("market_data_provider"),
        },
    )


def _clear_blocked(trade_id):
    with _blocked_lock:
        _blocked_trades.discard(trade_id)


def _retain_active_blocked(active):
    with _blocked_lock:
        _blocked_trades.intersection_update(active)


def value_trade(trade):
    meta = trade.get("metadata") or {}
    provider = cache.trade_provider(trade) if cache.needs_spot(trade) else None
    inputs = market_inputs(trade["asset_class"], trade["symbol"], meta, provider)
    priced = price_from_inputs(trade["asset_class"], meta, inputs)
    if priced is None:
        return None
    price, multiplier = priced
    spot = inputs.get("spot") or {}
    curve = inputs.get("curve") or {}
    projection = inputs.get("projection_curve") or {}
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
        "market_data_provider": spot.get("provider") or curve.get("provider"),
        "market_data_timestamp": spot.get("provider_timestamp") or (
            f"{curve['as_of_date']}T00:00:00+00:00" if curve.get("as_of_date") else None
        ),
        "valuation_time": get_iso_timestamp(),
        "valuation_payload": {
            "current_price": str(price),
            "multiplier": multiplier,
            **({"discount_curve": curve.get("curve_name"),
                "curve_as_of": curve.get("as_of_date"),
                "curve_received_at": curve.get("received_at")} if curve else {}),
            **({"projection_curve": meta["projection_curve"],
                "projection_curve_as_of": projection.get("as_of_date"),
                "projection_curve_received_at": projection.get("received_at")}
               if meta.get("projection_curve") else {}),
            **({"underlying_symbol": meta["underlying_symbol"]}
               if meta.get("underlying_symbol") else {}),
            **({"face_value": meta["face_value"]}
               if meta.get("face_value") else {}),
            "contract_terms": {
                key: meta[key]
                for key in (
                    "coupon_rate",
                    "fixed_rate",
                    "maturity_years",
                    "option_type",
                    "strike",
                    "underlying_symbol",
                )
                if meta.get(key) is not None
            },
        },
    }


def _value_and_store(trades):
    events = []
    for trade in trades:
        valuation = value_trade(trade)
        if valuation is None:
            _audit_blocked(trade)
            continue
        persisted = repository.save_valuation(valuation)
        if persisted == repository.VALUATION_PERSIST_BLOCKED:
            continue
        _clear_blocked(valuation["trade_id"])
        if not cache.record_valuation(valuation):
            log.debug("valuation_after_final_dropped", trade_id=valuation["trade_id"])
            continue
        log.debug("valuation_computed", trade_id=valuation["trade_id"],
                  symbol=valuation["symbol"])
        events.append(valuation)
    return events


def value_quote(provider, symbol):
    return _value_and_store(cache.trades_for_quote(provider, symbol))


def value_curve(curve_name):
    return _value_and_store(cache.trades_for_curve(curve_name))


def value_all_active():
    """Revalue the full active set after a complete market-state reconciliation."""
    return _value_and_store(cache.active_trades_snapshot())


def refresh_active_trades():
    active = repository.load_active_trades()
    _retain_active_blocked(active)
    dirty, first_load = cache.replace_active_trades(active)
    if first_load:
        log.info("active_set_bootstrapped", trades=len(active))
    else:
        for trade in dirty:
            log.info(
                "trade_entered_or_changed_active_set",
                trade_id=trade["trade_id"],
                symbol=trade["symbol"],
                book_id=trade["book_id"],
            )
    return dirty


def restore_terminal_valuations():
    """Populate the seed cache before the HTTP server accepts subscribers."""
    terminals = repository.load_terminal_valuations()
    for valuation in terminals:
        cache.record_valuation(valuation)
    log.info("terminal_valuations_restored", valuations=len(terminals))


def trade_refresh_loop():
    while True:
        try:
            for event in _value_and_store(refresh_active_trades()):
                publish_valuation(event)
            finals = repository.finalize_closed_trades()
            cache.remove_active_trades(valuation["trade_id"] for valuation in finals)
            for valuation in finals:
                cache.record_valuation(valuation)
                publish_valuation(valuation)
        except Exception:
            log.exception("refresh_failed")
        time.sleep(TRADE_REFRESH_SECONDS)
