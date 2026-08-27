import queue

from pricing_service import cache
from pricing_service.config import SERVICE_NAME
from desk_runtime.logging_config import get_logger

log = get_logger(SERVICE_NAME)
STREAM_OVERFLOW = object()


def _publish(event_type, data):
    with cache.clients_lock:
        targets = list(cache.client_event_queues)
    message = {"event": event_type, "data": data}
    for client_queue in targets:
        try:
            client_queue.put_nowait(message)
        except queue.Full:
            try:
                while True:
                    client_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                client_queue.put_nowait(STREAM_OVERFLOW)
            except queue.Full:
                pass
            log.warning("stream_client_overflow_reconnect_required", event_type=event_type)


def publish_valuation(pricing_event):
    if not cache.is_current_valuation(pricing_event):
        log.debug("superseded_valuation_not_published", trade_id=pricing_event["trade_id"])
        return
    _publish("valuation_update", pricing_event)


def publish_book_risk(book_risk_event):
    _publish("book_risk_update", book_risk_event)
