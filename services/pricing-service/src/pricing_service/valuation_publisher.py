
from pricing_service import cache
from pricing_service.config import SERVICE_NAME
from desk_runtime.logging_config import get_logger
from desk_runtime.streams import STREAM_OVERFLOW, publish_event

log = get_logger(SERVICE_NAME)



def _publish(event_type, data):
    publish_event(cache.client_event_queues, cache.clients_lock, event_type, data, log)


def publish_valuation(pricing_event):
    if not cache.is_current_valuation(pricing_event):
        log.debug("superseded_valuation_not_published", trade_id=pricing_event["trade_id"])
        return
    _publish("valuation_update", pricing_event)


def publish_book_risk(book_risk_event):
    _publish("book_risk_update", book_risk_event)
