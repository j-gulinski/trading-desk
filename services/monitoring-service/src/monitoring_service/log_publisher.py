import queue
import threading

CLIENT_QUEUE_SIZE = 500

_clients_lock = threading.Lock()
_client_queues = set()


def register():
    client_queue = queue.Queue(maxsize=CLIENT_QUEUE_SIZE)
    with _clients_lock:
        _client_queues.add(client_queue)
    return client_queue


def unregister(client_queue):
    with _clients_lock:
        _client_queues.discard(client_queue)


def publish_line(record):
    with _clients_lock:
        targets = list(_client_queues)
    for client_queue in targets:
        try:
            client_queue.put_nowait(record)
        except queue.Full:
            pass
