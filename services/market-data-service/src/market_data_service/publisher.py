import threading
import uuid

from desk_runtime.functions import utcnow
from desk_runtime.logging_config import get_logger
from desk_runtime.streams import EventHub
from market_data_service.config import SERVICE_NAME

log = get_logger(SERVICE_NAME)
hub = EventHub(log)

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
    hub.publish(event_type, tick)


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
