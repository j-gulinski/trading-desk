import queue
import bottle
from bottle import request, response

from pricing_service import cache
from pricing_service.config import SERVICE_NAME, VALUATION_STREAM_QUEUE_SIZE
from pricing_service.market_inputs import market_inputs
from desk_domain.instruments import instrument_for
from desk_runtime.config import DEFAULT_QUOTE_PROVIDER
from pricing_service.schemas import ScenarioRequest
from pricing_service.valuation_publisher import STREAM_OVERFLOW
from desk_domain.curve_registry import latest_curve_sets
from desk_pricing.provenance import pricing_provenance
from desk_runtime.db import session_scope
from desk_domain.active_set import load_active_set
from desk_domain.symbols import watchlist_spot_catalog
from desk_domain.term_schemas import validate_terms
from pricing_service.scenario import run_scenario
from desk_runtime.http import json_error, json_response
from desk_runtime.serialization import to_json
from desk_runtime.logging_config import get_logger

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
    return json_response(cache.all_valuations())


@app.route("/book-risk")
def get_book_risk():
    return json_response(cache.all_book_risk())


@app.route("/price", method="POST")
def price_preview():
    body = request.json
    if not isinstance(body, dict):
        return json_error("request body must be an object", 400)
    symbol = body.get("symbol")
    if symbol is not None and not isinstance(symbol, str):
        return json_error("symbol must be text", 400)
    if body.get("terms") is not None:
        with session_scope() as session:
            spot_catalog = watchlist_spot_catalog(session)
            curves = latest_curve_sets(session)
        terms, error = validate_terms(body.get("asset_class"), body["terms"],
                                      spot_catalog, curves)
        if terms is None:
            log.warning("price_preview_rejected", symbol=symbol,
                        asset_class=body.get("asset_class"), reason=error)
            return json_error(error, 400, symbol=symbol)
    else:
        with session_scope() as session:
            entry = load_active_set(session).get((symbol or "").strip().upper())
        terms = (
            {"asset_class": entry.asset_class, "currency": entry.currency}
            if entry is not None else None
        )
        if terms is None:
            log.warning("price_preview_rejected", symbol=symbol, reason="instrument not found")
            return json_error("instrument not found", 404, symbol=symbol)
    raw_provider = body.get("market_data_provider")
    if raw_provider is not None and not isinstance(raw_provider, str):
        return json_error("market_data_provider must be text", 400)
    provider = (raw_provider or "").strip().upper() or None
    try:
        instrument = instrument_for(terms["asset_class"], symbol, terms)
    except (TypeError, ValueError) as exc:
        return json_error(str(exc), 400, symbol=symbol)
    inputs = market_inputs(instrument, provider)
    priced = instrument.price(inputs)
    if priced is None:
        log.warning("price_preview_unavailable", symbol=symbol,
                    asset_class=terms["asset_class"], provider=provider)
        return json_error(
            f"{provider or DEFAULT_QUOTE_PROVIDER} has no current quote for {symbol}"
            if not instrument.uses_curve()
            else "the selected curve (or the underlying quote) is not available yet",
            503,
            symbol=symbol,
        )
    revisions = _preview_revisions(terms, inputs)
    if not _revisions_match(body.get("expected_market_revisions"), revisions):
        return json_error(
            "pricing market data is catching up; retry the preview", 409,
            market_revisions=revisions,
        )
    needs_spot = instrument.needs_quote
    provenance = pricing_provenance(
        instrument.model, inputs.get("curve"), inputs.get("projection_curve"),
    )
    log.info("price_preview", symbol=symbol, asset_class=terms["asset_class"],
             provider=provider, price=str(priced["price"]))
    return json_response({
        "symbol": symbol,
        "asset_class": terms["asset_class"],
        "currency": terms.get("currency", "USD"),
        "market_data_provider": (provider or DEFAULT_QUOTE_PROVIDER) if needs_spot else None,
        **priced,
        "market_revisions": revisions,
        **({"pricing_provenance": provenance} if provenance else {}),
    })


@app.route("/valuations/<trade_id>")
def get_valuation(trade_id):
    valuation = cache.get_valuation(trade_id)
    if valuation is None:
        return json_error("valuation not found", 404, trade_id=trade_id)
    return json_response(valuation)


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
    body = request.json
    if body is None:
        return json_error("invalid JSON or missing Content-Type: application/json", 400)

    try:
        req = ScenarioRequest.from_body(body)
    except ValueError as e:
        return json_error(str(e), 400)

    if type(req.instrument).fields:
        with session_scope() as session:
            spot_catalog = watchlist_spot_catalog(session)
            curves = latest_curve_sets(session)
        terms, error = validate_terms(
            req.instrument.asset_class, req.instrument.as_terms(), spot_catalog, curves,
        )
        if terms is None:
            return json_error(error, 400)
        req.instrument = instrument_for(
            req.instrument.asset_class, req.instrument.symbol, terms,
        )

    try:
        result = run_scenario(req)
    except (ValueError, ArithmeticError) as error:
        return json_error(str(error), 400)
    if result is None:
        return json_error("market data not found for instrument", 404)

    return json_response(result)


@app.route("/health")
def health():
    return json_response({
        "service": SERVICE_NAME,
        "status": "UP",
        **cache.health_snapshot(),
    })
