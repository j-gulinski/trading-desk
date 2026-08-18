import threading
import uuid

data_lock = threading.Lock()
stream_id = str(uuid.uuid4())

spots = {}
curves = {}


def current_snapshot() -> dict:
    with data_lock:
        return {
            "stream_id": stream_id,
            "event_id": None,
            "spots": {key: dict(value) for key, value in spots.items()},
            "curves": {key: dict(value) for key, value in curves.items()},
        }
