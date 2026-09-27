from pricing_service import cache
from pricing_service.config import SERVICE_NAME, VALUATION_STREAM_QUEUE_SIZE
from desk_runtime.logging_config import get_logger
from desk_runtime.streams import EventHub

log = get_logger(SERVICE_NAME)
hub = EventHub(log, VALUATION_STREAM_QUEUE_SIZE)


def publish_valuation(pricing_event):
    if not cache.is_current_valuation(pricing_event):
        log.debug("superseded_valuation_not_published", trade_id=pricing_event["trade_id"])
        return
    hub.publish("valuation_update", pricing_event)


def publish_book_risk(book_risk_event):
    hub.publish("book_risk_update", book_risk_event)
