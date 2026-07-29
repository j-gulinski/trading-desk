import queue
from app import cache
from app.config import SERVICE_NAME
from shared.logging_config import get_logger

log = get_logger(SERVICE_NAME)


def publish_valuation(pricing_event):
    with cache.data_lock:
        if cache.latest_valuations.get(pricing_event["trade_id"]) is not pricing_event:
            log.debug("superseded_valuation_not_published", trade_id=pricing_event["trade_id"])
            return

        with cache.clients_lock:
            targets = list(cache.client_event_queues)
        for q in targets:
            try:
                q.put_nowait(pricing_event)
            except queue.Full:
                log.debug("client_dropped")
