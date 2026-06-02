import queue
import logging
from app import cache

def publish_valuation(pricing_event):
    with cache.clients_lock:
        targets = list(cache.client_event_queues)
    for q in targets:
        try:
            q.put_nowait(pricing_event)
        except queue.Full:
            logging.debug("Dropped tick for slow client")
