import queue
import logging
import threading

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
            logging.debug("Dropped event for slow client")
