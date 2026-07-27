import queue
import threading

from shared.logging_config import get_logger
from app.config import SERVICE_NAME

log = get_logger(SERVICE_NAME)
clients_lock = threading.Lock()
client_event_queues = set()


def publish_tick(event_type, tick):
    message = {"event": event_type, "data": tick}
    with clients_lock:
        targets = list(client_event_queues)
    for q in targets:
        try:
            q.put_nowait(message)
        except queue.Full:
            log.debug("client_event_dropped")
