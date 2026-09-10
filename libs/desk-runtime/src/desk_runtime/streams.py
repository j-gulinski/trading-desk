import json
import queue

STREAM_OVERFLOW = object()


def publish_event(queues, lock, event_type, data, log):
    with lock:
        targets = list(queues)
    for target in targets:
        try:
            target.put_nowait({"event": event_type, "data": data})
        except queue.Full:
            # A dropped valuation/quote requires a fresh snapshot, not a silent gap.
            try:
                while True:
                    target.get_nowait()
            except queue.Empty:
                pass
            try:
                target.put_nowait(STREAM_OVERFLOW)
            except queue.Full:
                pass
            log.warning("stream_client_overflow_reconnect_required", event_type=event_type)


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
