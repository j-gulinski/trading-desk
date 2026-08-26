import queue
import bottle
from bottle import request, response

from app import cache
from app.config import SERVICE_NAME, VALUATION_STREAM_QUEUE_SIZE
from app.pricers.registry import market_inputs, price_details, price_from_inputs
from shared.config import DEFAULT_QUOTE_PROVIDER
from app.schemas import ScenarioRequest
from app.valuation_publisher import STREAM_OVERFLOW
from shared.curve_registry import latest_curve_sets
from shared.db import session_scope
from shared.active_set import load_active_set
from shared.symbols import (
    CURVE_PRICED_ASSET_CLASSES,
    SPOT_ASSET_CLASSES,
    watchlist_option_underlying_symbols,
    watchlist_spot_currencies,
)
from shared.term_schemas import validate_terms
from app.scenario import run_scenario
from shared.serialization import to_json
from shared.logging_config import get_logger

log = get_logger(SERVICE_NAME)
app = bottle.Bottle()


def _preview_revisions(terms, inputs):
    spot = inputs.get("spot") or {}

    def spot_revision():
        if not spot:
            return None
        return {
            "provider": spot.get("provider"),
            "symbol": spot.get("symbol"),
            "provider_timestamp": spot.get("provider_timestamp"),
            "received_at": spot.get("received_at"),
        }

    def curve_revision(field, input_name):
        curve = inputs.get(input_name) or {}
        if not curve:
            return None
        return {
            "curve_name": terms.get(field),
            "as_of_date": curve.get("as_of_date"),
            "received_at": curve.get("received_at"),
        }

    return {
        "spot": spot_revision(),
        "discount_curve": curve_revision("discount_curve", "curve"),
        "projection_curve": curve_revision("projection_curve", "projection_curve"),
    }


def _revisions_match(expected, actual):
    if expected is None:
        return True
    if not isinstance(expected, dict):
        return False
    for role, wanted in expected.items():
        if wanted is None:
            continue
        used = actual.get(role)
        if not isinstance(wanted, dict) or not isinstance(used, dict):
            return False
        for field, value in wanted.items():
            if value is not None and str(used.get(field)) != str(value):
                return False
    return True


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
    body = request.json
    if not isinstance(body, dict):
        response.status = 400
        return to_json({"error": "request body must be an object"})
    symbol = body.get("symbol")
    if symbol is not None and not isinstance(symbol, str):
        response.status = 400
        return to_json({"error": "symbol must be text"})
    if body.get("terms") is not None:
        with session_scope() as session:
            underlying_choices = watchlist_option_underlying_symbols(session)
            underlying_currencies = watchlist_spot_currencies(session)
            curves = latest_curve_sets(session)
        terms, error = validate_terms(body.get("asset_class"), body["terms"],
                                      underlying_choices, curves,
                                      underlying_currencies)
        if terms is None:
            log.warning("price_preview_rejected", symbol=symbol,
                        asset_class=body.get("asset_class"), reason=error)
            response.status = 400
            return to_json({"error": error, "symbol": symbol})
    else:
        with session_scope() as session:
            entry = load_active_set(session).get((symbol or "").strip().upper())
        terms = (
            {"asset_class": entry.asset_class, "currency": entry.currency}
            if entry is not None else None
        )
        if terms is None:
            log.warning("price_preview_rejected", symbol=symbol, reason="instrument not found")
            response.status = 404
            return to_json({"error": "instrument not found", "symbol": symbol})
    raw_provider = body.get("market_data_provider")
    if raw_provider is not None and not isinstance(raw_provider, str):
        response.status = 400
        return to_json({"error": "market_data_provider must be text"})
    provider = (raw_provider or "").strip().upper() or None
    inputs = market_inputs(terms["asset_class"], symbol, terms, provider)
    priced = price_from_inputs(terms["asset_class"], terms, inputs)
    if priced is None:
        log.warning("price_preview_unavailable", symbol=symbol,
                    asset_class=terms["asset_class"], provider=provider)
        response.status = 503
        return to_json({
            "error": f"{provider or DEFAULT_QUOTE_PROVIDER} has no current quote for {symbol}"
            if terms["asset_class"] in SPOT_ASSET_CLASSES
            else "the selected curve (or the underlying quote) is not available yet",
            "symbol": symbol,
        })
    price, multiplier = priced
    revisions = _preview_revisions(terms, inputs)
    if not _revisions_match(body.get("expected_market_revisions"), revisions):
        response.status = 409
        return to_json({
            "error": "pricing market data is catching up; retry the preview",
            "market_revisions": revisions,
        })
    needs_spot = (
        terms["asset_class"] in SPOT_ASSET_CLASSES
        or terms["asset_class"] == "EUROPEAN_OPTION"
    )
    log.info("price_preview", symbol=symbol, asset_class=terms["asset_class"],
             provider=provider, price=str(price))
    return to_json({
        "symbol": symbol,
        "asset_class": terms["asset_class"],
        "currency": terms.get("currency", "USD"),
        "market_data_provider": (provider or DEFAULT_QUOTE_PROVIDER) if needs_spot else None,
        "price": price,
        "multiplier": multiplier,
        "market_revisions": revisions,
        **price_details(terms["asset_class"], terms, inputs),
        **(
            {"projection_curve_tracks_index": terms["projection_curve_tracks_index"]}
            if "projection_curve_tracks_index" in terms else {}
        ),
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
                if message is STREAM_OVERFLOW:
                    log.warning("stream_client_disconnected_after_overflow")
                    return
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

    if req.position.instrument.asset_class in CURVE_PRICED_ASSET_CLASSES:
        with session_scope() as session:
            underlying_choices = watchlist_option_underlying_symbols(session)
            underlying_currencies = watchlist_spot_currencies(session)
            curves = latest_curve_sets(session)
        terms, error = validate_terms(
            req.position.instrument.asset_class,
            req.position.instrument.meta,
            underlying_choices,
            curves,
            underlying_currencies,
        )
        if terms is None:
            response.status = 400
            return to_json({"error": error})
        req.position.instrument.meta = terms

    result = run_scenario(req)
    if result is None:
        response.status = 404
        return to_json({"error": "market data not found for instrument"})

    return to_json(result)


@app.route("/health")
def health():
    return {
        "service": SERVICE_NAME,
        "status": "UP",
        **cache.health_snapshot(),
    }
