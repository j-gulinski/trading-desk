import queue
import threading
from collections import OrderedDict, deque

from app.config import TRADE_ACTION_QUEUE_SIZE

intents = queue.Queue(maxsize=TRADE_ACTION_QUEUE_SIZE)

LATENCY_WINDOW = 50

_stats_lock = threading.Lock()
stats = {
    "accepted": 0,
    "processed": 0,
    "created": 0,
    "closed": 0,
    "reassigned": 0,
    "rejected": 0,
    "duplicates": 0,
}
_latencies_ms = deque(maxlen=LATENCY_WINDOW)
_accepted_open_requests = OrderedDict()
ACCEPTED_REQUEST_WINDOW = 5000


def enqueue(intent):
    try:
        intents.put_nowait(intent)
    except queue.Full:
        return False
    incr("accepted")
    request_id = intent.get("client_request_id")
    trade_id = intent.get("trade_id")
    if intent.get("action_type") == "OPEN_TRADE" and request_id and trade_id:
        with _stats_lock:
            _accepted_open_requests[request_id] = trade_id
            _accepted_open_requests.move_to_end(request_id)
            while len(_accepted_open_requests) > ACCEPTED_REQUEST_WINDOW:
                _accepted_open_requests.popitem(last=False)
    return True


def accepted_trade_id(client_request_id):
    with _stats_lock:
        return _accepted_open_requests.get(client_request_id)


def incr(key, n=1):
    with _stats_lock:
        stats[key] += n


def record_processed(elapsed_ms):
    with _stats_lock:
        stats["processed"] += 1
        _latencies_ms.append(elapsed_ms)


def queue_status():
    with _stats_lock:
        snapshot = dict(stats)
        latencies = list(_latencies_ms)
    snapshot["queued"] = intents.qsize()
    snapshot["last_processing_ms"] = latencies[-1] if latencies else None
    snapshot["avg_processing_ms"] = (
        round(sum(latencies) / len(latencies), 1) if latencies else None
    )
    return snapshot
