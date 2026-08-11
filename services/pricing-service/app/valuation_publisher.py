import queue

from app import cache
from app.config import SERVICE_NAME
from shared.logging_config import get_logger

log = get_logger(SERVICE_NAME)


def _publish(event_type, data):
    with cache.clients_lock:
        targets = list(cache.client_event_queues)
    message = {"event": event_type, "data": data}
    for client_queue in targets:
        try:
            client_queue.put_nowait(message)
        except queue.Full:
            log.debug("client_dropped", event_type=event_type)


def publish_valuation(pricing_event):
    with cache.data_lock:
        if cache.latest_valuations.get(pricing_event["trade_id"]) is not pricing_event:
            log.debug("superseded_valuation_not_published", trade_id=pricing_event["trade_id"])
            return
    _publish("valuation_update", pricing_event)


def publish_book_risk(book_risk_event):
    _publish("book_risk_update", book_risk_event)
