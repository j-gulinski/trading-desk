import json
import queue
import threading
import time
import urllib.error
import urllib.request

from desk_runtime.serialization import to_json

_OVERFLOW = object()


class EventHub:
    """Server-sent events fanned out to every connected client of one service."""

    def __init__(self, log, queue_size=500):
        self._log = log
        self._queue_size = queue_size
        self._lock = threading.Lock()
        self._clients = set()

    def publish(self, event_type, data):
        frame = f"event: {event_type}\ndata: {to_json(data)}\n\n"
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            try:
                client.put_nowait(frame)
            except queue.Full:
                self._disconnect(client)
                self._log.warning("stream_client_overflow_reconnect_required", event_type=event_type)

    def subscribe(self, first_frame=": connected\n\n"):
        client = queue.Queue(maxsize=self._queue_size)
        with self._lock:
            self._clients.add(client)
        self._log.info("stream_client_connected")
        return self._frames(client, first_frame)

    def _frames(self, client, first_frame):
        try:
            yield first_frame
            while (frame := client.get()) is not _OVERFLOW:
                yield frame
        finally:
            with self._lock:
                self._clients.discard(client)
            self._log.info("stream_client_disconnected")

    @staticmethod
    def _disconnect(client):
        try:
            while True:
                client.get_nowait()
        except queue.Empty:
            pass
        try:
            client.put_nowait(_OVERFLOW)
        except queue.Full:
            pass


def read_events(stream):
    event, data = "message", []
    for raw in stream:
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if data:
                yield event, json.loads("\n".join(data))
            event, data = "message", []
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))


def follow_stream(url, reconcile, handle, on_state, log, retry_seconds=5):
    """Hold one SSE connection open for a background thread, reconnecting forever.

    After each connect, reconcile() loads the snapshot and returns a checkpoint that is
    passed to handle(event_type, data, checkpoint). on_state(connected) runs only when
    the connection state changes.
    """
    connected = False
    while True:
        log.info("stream_connecting", url=url)
        try:
            with urllib.request.urlopen(url) as stream:
                connected = True
                on_state(True)
                checkpoint = reconcile()
                for event_type, data in read_events(stream):
                    handle(event_type, data, checkpoint)
        except urllib.error.URLError as error:
            log.warning("stream_failed", error=str(error))
        except Exception:
            log.exception("stream_error")
        if connected:
            connected = False
            try:
                on_state(False)
            except Exception:
                log.exception("stream_state_update_failed")
        time.sleep(retry_seconds)
