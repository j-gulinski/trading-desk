"""Checkpointed Market Data SSE consumer and targeted valuation dispatcher."""

import time
import json
import urllib.request
import urllib.error

from desk_domain.audit import write_audit
from desk_runtime.config import BENCHMARK_PROVIDER, BENCHMARK_SYMBOL
from desk_runtime.functions import first_present
from desk_runtime.logging_config import get_logger
from pricing_service import cache
from pricing_service.config import MARKET_DATA_STREAM_URL, SERVICE_NAME
from pricing_service.book_risk import sample_and_publish
from pricing_service.valuation_engine import value_all_active, value_curve, value_quote
from pricing_service.valuation_publisher import publish_valuation

log = get_logger(SERVICE_NAME)


def _audit(event_type, message, severity="INFO"):
    try:
        write_audit(SERVICE_NAME, event_type, message, severity=severity)
    except Exception:
        log.exception("audit_write_failed", event_type=event_type)


def _set_connection(state):
    return cache.set_market_data_connection(state)


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
        level = first_present(tick, ("mid", "last"))
        if level is not None:
            sample_and_publish(level)


def _snapshot_url():
    return MARKET_DATA_STREAM_URL.rsplit("/", 1)[0] + "/snapshot"


def _reconcile_market_state():
    """Replace local state from a snapshot and return its stream checkpoint.

    The caller opens the SSE response first. Events emitted while this request runs
    are therefore queued by Market Data and can be consumed after the snapshot.
    """
    try:
        with urllib.request.urlopen(_snapshot_url(), timeout=10) as response:
            snapshot = json.loads(response.read())
        cache.replace_market_state(
            snapshot.get("spots") or {}, snapshot.get("curves") or {}
        )
    except Exception as error:
        log.warning("market_state_reconcile_failed", error=str(error))
        return None

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


def market_data_stream_consumer():
    while True:
        log.info("stream_connecting", url=MARKET_DATA_STREAM_URL)
        try:
            request = urllib.request.Request(MARKET_DATA_STREAM_URL)
            with urllib.request.urlopen(request) as stream:
                if _set_connection("CONNECTED"):
                    _audit("STREAM_CONNECTED", "Connected to market data stream")
                checkpoint = _reconcile_market_state()
                if checkpoint is None:
                    raise RuntimeError("market-data snapshot reconciliation failed")
                event_type = None
                for raw in stream:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    if line.startswith("event:"):
                        event_type = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        tick = json.loads(line[len("data:"):].strip())
                        if _at_or_before_checkpoint(tick, checkpoint):
                            continue
                        _handle(event_type, tick)
        except urllib.error.URLError as e:
            log.warning("stream_failed", error=str(e))
        except Exception:
            log.exception("stream_error")
        finally:
            if _set_connection("RECONNECTING"):
                _audit("STREAM_DISCONNECTED", "Market data stream disconnected", severity="WARNING")
        time.sleep(5)
