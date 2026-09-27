"""Pricing, revaluation routing, and the active-trade polling loop."""

import time
import threading
from datetime import datetime

from pricing_service import cache, repository
from decimal import Decimal
from desk_pricing.valuation import pnl, position_value, record_totals, signed_quantity
from pricing_service.market_inputs import market_inputs
from desk_domain.instruments import instrument_for, type_view_for
from pricing_service.valuation_publisher import publish_valuation
from pricing_service.config import SERVICE_NAME, TRADE_REFRESH_SECONDS, VALUATION_WRITE_INTERVAL_SECONDS
from desk_pricing.provenance import pricing_provenance
from desk_runtime.functions import get_iso_timestamp, utcnow
from desk_runtime.logging_config import get_logger
from desk_domain.audit import write_audit
from desk_domain.contract_data import split_terms
from desk_domain.curves import curve_stale_at

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


def _valuation_state(spot, curve):
    """LIVE / MARKET_CLOSED / STALE while the inputs stay fresh, and when they turn stale."""
    status, deadlines = "LIVE", []
    if spot:
        if spot.get("freshness") in (None, "MISSING"):
            status = "STALE"
        elif spot.get("freshness") == "CLOSED":
            status = "MARKET_CLOSED"
        if spot.get("stale_at"):
            deadlines.append(datetime.fromisoformat(str(spot["stale_at"])))
    if curve:
        deadlines.append(curve_stale_at(curve["curve_name"], curve["as_of_date"]))
    known = [deadline for deadline in deadlines if deadline is not None]
    return status, min(known) if known else None


def _curve_move_bps(meta, provenance):
    def maturity_rate(record):
        return ((record or {}).get("curves") or {}).get("discount", {}).get("maturity_rate_percent")

    entry, current = maturity_rate(meta.get("pricing_provenance")), maturity_rate(provenance)
    return (current - entry) * 100 if entry is not None and current is not None else None


def value_trade(trade):
    meta = trade.get("metadata") or {}
    instrument = instrument_for(trade["asset_class"], trade["symbol"], meta)
    provider = trade["market_data_provider"] if instrument.needs_quote else None
    inputs = market_inputs(instrument, provider)
    priced = instrument.price(inputs)
    if priced is None:
        return None
    price, multiplier = priced["price"], priced["multiplier"]
    spot = inputs.get("spot") or {}
    curve = inputs.get("curve") or {}
    maturity = getattr(instrument, "maturity_years", None)
    provenance = pricing_provenance(instrument.model, curve, maturity)
    status, stale_at = _valuation_state(spot, curve)
    quantity = trade["quantity"]
    fair_value = position_value(price, quantity, multiplier)
    unrealized = pnl(
        trade["side"], price, trade["trade_price"], quantity, multiplier
    )
    return {
        "trade_id": trade["trade_id"],
        "book_id": trade["book_id"],
        "book_name": trade["book_name"],
        "asset_class": trade["asset_class"],
        **type_view_for(trade["asset_class"]),
        "symbol": trade["symbol"],
        "currency": trade["currency"],
        "quantity": signed_quantity(trade["side"], quantity),
        "trade_price": trade["trade_price"],
        "fair_value": fair_value,
        "market_value": fair_value,
        "unrealized_pnl": unrealized,
        "realized_pnl": Decimal(0),
        "total_pnl": unrealized,
        **record_totals(trade["trade_price"], quantity, multiplier, unrealized),
        "market_data_provider": spot.get("provider") or curve.get("provider"),
        "market_data_timestamp": spot.get("provider_timestamp") or (
            f"{curve['as_of_date']}T00:00:00+00:00" if curve.get("as_of_date") else None
        ),
        "valuation_time": get_iso_timestamp(),
        "valuation_payload": {
            "status": status,
            "stale_at": stale_at,
            "current_price": str(price),
            "multiplier": multiplier,
            "pricing": split_terms(instrument).pricing,
            "spot_source": {
                key: spot.get(key) for key in ("provider", "provider_timestamp", "received_at")
            } if spot else None,
            **({"discount_curve": curve.get("curve_name"),
                "curve_as_of": curve.get("as_of_date"),
                "curve_received_at": curve.get("received_at")} if curve else {}),
            **({"curve_move_bps": curve_move}
               if (curve_move := _curve_move_bps(meta, provenance)) is not None else {}),
            **({"underlying_symbol": meta["underlying_symbol"]}
               if meta.get("underlying_symbol") else {}),
            **({"face_value": meta["face_value"]}
               if meta.get("face_value") else {}),
            **({"pricing_provenance": provenance} if provenance else {}),
        },
    }


def _value_and_store(trades):
    events = []
    for trade in trades:
        try:
            valuation = value_trade(trade)
        except Exception:
            log.exception(
                "valuation_failed",
                trade_id=trade.get("trade_id"),
                symbol=trade.get("symbol"),
            )
            _audit_blocked(trade)
            continue
        if valuation is None:
            _audit_blocked(trade)
            continue
        if cache.claim_valuation_write(valuation["trade_id"], utcnow(), VALUATION_WRITE_INTERVAL_SECONDS) \
                and not repository.save_valuation(valuation):
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
