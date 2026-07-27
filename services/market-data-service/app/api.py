import queue
import bottle
from bottle import response

from app import persistence
from app.publisher import clients_lock, client_event_queues
from app.health import get_health
from app.config import SERVICE_NAME
from shared.serialization import to_json
from shared.logging_config import get_logger

log = get_logger(SERVICE_NAME)
app = bottle.Bottle()


@app.route("/stream")
def stream():
    response.content_type = "text/event-stream"
    response.set_header("Cache-Control", "no-cache")
    with clients_lock:
        client_q = queue.Queue(maxsize=500)
        client_event_queues.add(client_q)
    log.info("stream_client_connected")

    def generate_events():
        try:
            while True:
                message = client_q.get()
                yield f"event: {message['event']}\ndata: {to_json(message['data'])}\n\n"
        except Exception as exc:
            log.debug("stream_client_error", error=type(exc).__name__)
        finally:
            with clients_lock:
                client_event_queues.discard(client_q)
            log.info("stream_client_disconnected")

    return generate_events()


@app.route("/snapshot")
def get_snapshot():
    response.content_type = "application/json"
    return to_json(persistence.current_snapshot())


@app.route("/health")
def health():
    return get_health()
