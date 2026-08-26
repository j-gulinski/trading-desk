import queue
import threading
import uuid

from shared.functions import utcnow
from shared.logging_config import get_logger
from app.config import SERVICE_NAME

log = get_logger(SERVICE_NAME)
clients_lock = threading.Lock()
client_event_queues = set()
STREAM_OVERFLOW = object()

stream_id = str(uuid.uuid4())
_event_lock = threading.Lock()
_event_id = 0


def _next_event_id():
    global _event_id
    with _event_lock:
        _event_id += 1
        return _event_id


def last_event_id():
    with _event_lock:
        return _event_id


def publish_tick(event_type, tick):
    message = {"event": event_type, "data": tick}
    with clients_lock:
        targets = list(client_event_queues)
    for q in targets:
        try:
            q.put_nowait(message)
        except queue.Full:
            # Keeping a live connection after a gap would leave consumers with corrupt
            # state. Force this client to reconnect; its snapshot handshake then repairs
            # the complete quote/curve map.
            try:
                while True:
                    q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(STREAM_OVERFLOW)
            except queue.Full:
                pass
            log.warning("stream_client_overflow_reconnect_required")


def publish_quote(tick):
    publish_tick(
        "market_tick", {**tick, "stream_id": stream_id, "event_id": _next_event_id()}
    )


def publish_curve(tick):
    publish_tick(
        "curve_tick", {**tick, "stream_id": stream_id, "event_id": _next_event_id()}
    )


def publish_removal(rows):
    publish_tick(
        "market_remove",
        {
            "rows": list(rows),
            "stream_id": stream_id,
            "event_id": _next_event_id(),
            "event_time": utcnow(),
        },
    )
