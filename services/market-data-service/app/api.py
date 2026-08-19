import queue
import bottle
from bottle import request, response

from app import persistence, scheduler
from app.publisher import client_event_queues, clients_lock, last_event_id, stream_id
from app.config import SERVICE_NAME
from shared.freshness import classify
from shared.functions import utcnow
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
        yield ": connected\n\n"
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


def _board_payload():
    rows = persistence.board_rows()
    for row in rows:
        row["stale_after_seconds"] = scheduler.stale_after_seconds(
            row["provider"], row["symbol"]
        )
        row["event_time"] = row["received_at"]
    return rows


@app.route("/snapshot")
def get_snapshot():
    response.content_type = "application/json"
    rows = _board_payload()
    return to_json({
        "stream_id": stream_id,
        "event_id": last_event_id() or None,
        "spots": {f"{row['provider']}:{row['symbol']}": row for row in rows},
        "curves": {},
    })


@app.route("/quotes")
def get_quotes():
    response.content_type = "application/json"
    now = utcnow()
    rows = _board_payload()
    for row in rows:
        row["freshness"] = classify(
            True, row["provider_timestamp"], now, row["stale_after_seconds"]
        )
    return to_json(rows)


@app.route("/providers")
def get_providers():
    response.content_type = "application/json"
    return to_json(scheduler.providers_overview())


@app.route("/providers/<name>/health")
def get_provider_health(name):
    response.content_type = "application/json"
    detail = scheduler.provider_health(name.upper())
    if detail is None:
        response.status = 404
        return to_json({"error": f"unknown provider: {name}"})
    return to_json(detail)


@app.route("/refresh", method="POST")
def refresh():
    response.content_type = "application/json"
    symbol = (request.query.symbol or "").strip().upper()
    if not symbol:
        response.status = 400
        return to_json({"error": "symbol query parameter is required"})
    tick, error, status = scheduler.refresh_symbol(symbol)
    if error is not None:
        response.status = status
        log.warning("manual_refresh_rejected", symbol=symbol, reason=error)
        return to_json({"error": error, "symbol": symbol})
    log.info("manual_refresh", symbol=symbol)
    return to_json(tick)
