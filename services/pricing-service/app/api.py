import queue
import bottle
from bottle import response

from app import cache
from app.config import SERVICE_NAME
from shared.serialization import to_json
from shared.logging_config import get_logger

log = get_logger(SERVICE_NAME)
app = bottle.Bottle()


@app.route("/valuations")
def get_valuations():
    response.content_type = "application/json"
    return to_json(cache.all_valuations())


@app.route("/valuations/<trade_id>")
def get_valuation(trade_id):
    response.content_type = "application/json"
    valuation = cache.get_valuation(trade_id)
    if valuation is None:
        response.status = 404
        return to_json({"error": "valuation not found", "trade_id": trade_id})
    return to_json(valuation)


@app.route("/valuation-stream")
def valuation_stream():
    response.content_type = "text/event-stream"
    with cache.clients_lock:
        client_q = queue.Queue(maxsize=500)
        cache.client_event_queues.add(client_q)
    log.info("stream_client_connected")

    def generate_events():
        try:
            while True:
                event = client_q.get()
                yield f"event: valuation_update\ndata: {to_json(event)}\n\n"
        except Exception:
            pass
        finally:
            with cache.clients_lock:
                cache.client_event_queues.discard(client_q)
            log.info("stream_client_disconnected")

    return generate_events()


@app.route("/health")
def health():
    with cache.data_lock:
        return {
            "service": SERVICE_NAME,
            "status": "UP",
            "market_data_connection": cache.market_data_connection,
            "received_events": cache.ticks_received,
            "active_trades": len(cache.active_trades),
            "last_market_event_time": cache.last_event_timestamp,
        }
