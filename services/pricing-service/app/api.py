import queue
import bottle
from bottle import request, response

from app import cache
from app.config import SERVICE_NAME, VALUATION_STREAM_QUEUE_SIZE
from app.schemas import ScenarioRequest
from app.valuation_engine import price_instrument
from shared.catalog import INSTRUMENT_CATALOG
from shared.term_schemas import validate_terms
from app.scenario import run_scenario
from shared.serialization import to_json
from shared.logging_config import get_logger

log = get_logger(SERVICE_NAME)
app = bottle.Bottle()


@app.route("/valuations")
def get_valuations():
    response.content_type = "application/json"
    return to_json(cache.all_valuations())


@app.route("/book-risk")
def get_book_risk():
    response.content_type = "application/json"
    return to_json(cache.all_book_risk())


@app.route("/price", method="POST")
def price_preview():
    response.content_type = "application/json"
    body = request.json or {}
    symbol = body.get("symbol")
    if body.get("terms") is not None:
        terms, error = validate_terms(body.get("asset_class"), body["terms"])
        if terms is None:
            response.status = 400
            return to_json({"error": error, "symbol": symbol})
    else:
        terms = INSTRUMENT_CATALOG.get(symbol)
        if terms is None:
            response.status = 404
            return to_json({"error": "instrument not found", "symbol": symbol})
    priced = price_instrument(terms["asset_class"], symbol, terms)
    if priced is None:
        response.status = 503
        return to_json({"error": "required market data is not available", "symbol": symbol})
    price, multiplier = priced
    return to_json({
        "symbol": symbol,
        "asset_class": terms["asset_class"],
        "currency": terms.get("currency", "USD"),
        "price": price,
        "multiplier": multiplier,
    })


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
    response.set_header("Cache-Control", "no-cache")
    with cache.clients_lock:
        client_q = queue.Queue(maxsize=VALUATION_STREAM_QUEUE_SIZE)
        cache.client_event_queues.add(client_q)
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
            with cache.clients_lock:
                cache.client_event_queues.discard(client_q)
            log.info("stream_client_disconnected")

    return generate_events()


@app.route("/scenario", method="POST")
def post_scenario():
    response.content_type = "application/json"
    body = request.json
    if body is None:
        response.status = 400
        return to_json({"error": "invalid JSON or missing Content-Type: application/json"})

    try:
        req = ScenarioRequest.from_body(body)
    except ValueError as e:
        response.status = 400
        return to_json({"error": str(e)})

    result = run_scenario(req)
    if result is None:
        response.status = 404
        return to_json({"error": "market data not found for instrument"})

    return to_json(result)


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
