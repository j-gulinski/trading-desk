import queue
import threading

intents = queue.Queue()

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


def enqueue(intent):
    intents.put(intent)
    incr("accepted")


def incr(key, n=1):
    with _stats_lock:
        stats[key] += n


def queue_status():
    with _stats_lock:
        snapshot = dict(stats)
    snapshot["queued"] = intents.qsize()
    return snapshot
