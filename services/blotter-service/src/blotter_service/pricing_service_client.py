import json
import urllib.request

from desk_domain.audit import write_audit
from desk_runtime.logging_config import get_logger
from desk_runtime.streams import follow_stream
from blotter_service import live_valuations
from blotter_service.config import SERVICE_NAME, VALUATION_SNAPSHOT_URL, VALUATION_STREAM_URL

log = get_logger(SERVICE_NAME)


def _reconcile_valuations():
    with urllib.request.urlopen(VALUATION_SNAPSHOT_URL, timeout=10) as response:
        rows = json.loads(response.read())
    if not isinstance(rows, list):
        raise ValueError("valuation snapshot is not a list")
    live_valuations.replace_all(rows)
    log.info("valuations_reconciled", valuations=len(rows), live=live_valuations.count())


def _handle(event_type, valuation, _checkpoint):
    if event_type == "valuation_update":
        live_valuations.record(valuation)


def _set_connected(connected):
    if connected:
        write_audit(SERVICE_NAME, "STREAM_CONNECTED", "Connected to valuation stream")
    else:
        write_audit(SERVICE_NAME, "STREAM_DISCONNECTED", "Valuation stream disconnected",
                    severity="WARNING")


def valuation_stream_consumer():
    follow_stream(VALUATION_STREAM_URL, _reconcile_valuations, _handle, _set_connected, log)
