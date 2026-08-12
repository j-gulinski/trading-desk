import queue
import threading
from collections import deque

intents = queue.Queue()

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


def enqueue(intent):
    intents.put(intent)
    incr("accepted")


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
