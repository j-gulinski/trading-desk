import threading
import queue
import logging

clients_lock = threading.Lock()
client_event_queues = set()

def publish_tick(tick):
    with clients_lock:
        targets = list(client_event_queues)
    for q in targets:
        try:
            q.put_nowait(tick)
        except queue.Full:
            logging.debug("Dropped tick for slow client")
