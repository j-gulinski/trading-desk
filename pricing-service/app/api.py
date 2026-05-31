import json
import queue
import logging
import bottle
from bottle import response
from app import persistence

app = bottle.Bottle()


@app.route("/valuations")
def get_valuations():
    response.content_type = "application/json"
    with persistence.data_lock:
        return json.dumps(persistence.market_state)


@app.route("/valuations/<instrument_id>")
def get_valuation(instrument_id):
    response.content_type = "application/json"
    with persistence.data_lock:
        if instrument_id in persistence.market_state:
            return json.dumps(persistence.market_state[instrument_id])
        return json.dumps({"error": "Instrument not found"})


@app.route("/stream")
def stream():
    response.content_type = "text/event-stream"
    with persistence.clients_lock:
        client_q = queue.Queue(maxsize=500)
        persistence.client_event_queues.add(client_q)
    logging.info("New client connected to /stream endpoint")

    def generate_events():
        try:
            while True:
                tick = client_q.get()
                yield f"event: valuation_update\ndata: {json.dumps(tick)}\n\n"
        except Exception:
            pass
        finally:
            with persistence.clients_lock:
                persistence.client_event_queues.discard(client_q)
            logging.info("Client disconnected from /stream endpoint")

    return generate_events()


@app.route("/health")
def health():
    with persistence.data_lock:
        return {
            "service": "pricing-service",
            "status": "UP",
            "market_data_connection": persistence.market_data_connection,
            "received_events": persistence.ticks_received,
            "last_market_event_time": persistence.last_event_timestamp,
        }
