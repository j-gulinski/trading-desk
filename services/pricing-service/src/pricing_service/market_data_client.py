"""Checkpointed Market Data SSE consumer and targeted valuation dispatcher."""

import json
import urllib.request

from desk_domain.audit import write_audit
from desk_runtime.config import BENCHMARK_PROVIDER, BENCHMARK_SYMBOL
from desk_runtime.logging_config import get_logger
from desk_runtime.streams import follow_stream
from pricing_service import cache
from pricing_service.config import MARKET_DATA_SNAPSHOT_URL, MARKET_DATA_STREAM_URL, SERVICE_NAME
from pricing_service.book_risk import sample_and_publish
from pricing_service.valuation_engine import value_all_active, value_curve, value_quote
from pricing_service.valuation_publisher import publish_valuation

log = get_logger(SERVICE_NAME)


def _handle(event_type, tick):
    cache.record_market_event(tick.get("event_time"))

    if event_type == "market_remove":
        cache.drop_spots(tick.get("rows") or [])
        return

    if event_type == "curve_tick":
        if not cache.update_curve(tick):
            return
        for event in value_curve(tick["curve_name"]):
            publish_valuation(event)
        return

    if not cache.update_spot(tick):
        return
    for event in value_quote(tick["provider"], tick["symbol"]):
        publish_valuation(event)
    if tick["symbol"] == BENCHMARK_SYMBOL and tick["provider"] == BENCHMARK_PROVIDER:
        if tick.get("mid") is not None:
            sample_and_publish(tick["mid"])


def _reconcile_market_state():
    """Replace local state from a snapshot and return its stream checkpoint.

    The caller opens the SSE response first. Events emitted while this request runs
    are therefore queued by Market Data and can be consumed after the snapshot.
    """
    try:
        with urllib.request.urlopen(MARKET_DATA_SNAPSHOT_URL, timeout=10) as response:
            snapshot = json.loads(response.read())
        cache.replace_market_state(
            snapshot.get("spots") or {}, snapshot.get("curves") or {}
        )
    except Exception as error:
        log.warning("market_state_reconcile_failed", error=str(error))
        raise RuntimeError("market-data snapshot reconciliation failed") from error

    spots = snapshot.get("spots") or {}
    curves = snapshot.get("curves") or {}
    checkpoint = {
        "stream_id": snapshot.get("stream_id"),
        "event_id": snapshot.get("event_id"),
    }
    log.info(
        "market_state_reconciled",
        spots=len(spots),
        curves=len(curves),
        stream_id=checkpoint["stream_id"],
        event_id=checkpoint["event_id"],
    )
    try:
        events = value_all_active()
        for event in events:
            publish_valuation(event)
        log.info("active_trades_revalued_after_reconcile", valuations=len(events))
    except Exception:
        log.exception("reconciled_active_trade_revaluation_failed")
    return checkpoint


def _at_or_before_checkpoint(tick, checkpoint):
    if not checkpoint or tick.get("stream_id") != checkpoint.get("stream_id"):
        return False
    try:
        event_id = int(tick.get("event_id"))
        checkpoint_id = int(checkpoint.get("event_id"))
    except (TypeError, ValueError):
        return False
    return event_id <= checkpoint_id


def _handle_after_checkpoint(event_type, tick, checkpoint):
    if not _at_or_before_checkpoint(tick, checkpoint):
        _handle(event_type, tick)


def _set_connected(connected):
    cache.set_market_data_connection("CONNECTED" if connected else "RECONNECTING")
    if connected:
        write_audit(SERVICE_NAME, "STREAM_CONNECTED", "Connected to market data stream")
    else:
        write_audit(SERVICE_NAME, "STREAM_DISCONNECTED", "Market data stream disconnected",
                    severity="WARNING")


def market_data_stream_consumer():
    follow_stream(MARKET_DATA_STREAM_URL, _reconcile_market_state, _handle_after_checkpoint,
                  _set_connected, log)
