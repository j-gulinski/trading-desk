import math

import bottle
from bottle import request, response

from pricing_service import cache
from pricing_service.config import SERVICE_NAME
from pricing_service.market_inputs import market_inputs
from desk_domain.instruments import IRS_PAYMENTS_PER_YEAR, instrument_for
from desk_runtime.config import DEFAULT_QUOTE_PROVIDER
from pricing_service.schemas import ScenarioRequest
from pricing_service.valuation_publisher import hub
from desk_pricing.curves import curve_position, discount_factor, par_rate, rate_at
from desk_pricing.provenance import pricing_provenance
from desk_runtime.db import session_scope
from desk_domain.active_set import load_active_set
from desk_domain.term_schemas import checked_terms
from pricing_service.scenario import run_scenario
from desk_runtime.http import json_error, json_response
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

    def curve_revision():
        curve = inputs.get("curve") or {}
        if not curve:
            return None
        return {
            "curve_name": terms.get("discount_curve"),
            "as_of_date": curve.get("as_of_date"),
            "received_at": curve.get("received_at"),
        }

    return {"spot": spot_revision(), "discount_curve": curve_revision()}


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


def _positive_number(name):
    try:
        value = float(request.query.get(name, ""))
    except ValueError:
        raise ValueError(f"{name} must be a number") from None
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


@app.route("/curves/<curve_name>/at")
def curve_at(curve_name):
    try:
        maturity = _positive_number("maturity_years")
        index_tenor = request.query.get("index_tenor")
        if index_tenor:
            if index_tenor not in IRS_PAYMENTS_PER_YEAR:
                raise ValueError("index_tenor must be 3M or 6M")
            payments_per_year = IRS_PAYMENTS_PER_YEAR[index_tenor]
        elif request.query.get("payments_per_year"):
            payments_per_year = _positive_number("payments_per_year")
            if not payments_per_year.is_integer():
                raise ValueError("payments_per_year must be a whole number")
            payments_per_year = int(payments_per_year)
        else:
            payments_per_year = None
    except ValueError as error:
        return json_error(str(error), 400)
    with cache.data_lock:
        curve = cache.curves.get(curve_name)
    if curve is None:
        return json_error("curve is not loaded yet", 404, curve_name=curve_name)
    rate = rate_at(curve["tenors"], curve["rates"], maturity)
    par = par_rate(curve, maturity, payments_per_year) if payments_per_year else None
    return json_response({
        "curve_name": curve_name,
        "as_of_date": curve.get("as_of_date"),
        "maturity_years": maturity,
        "zero_rate_percent": rate * 100,
        "discount_factor": discount_factor(curve, maturity),
        **curve_position(curve["tenors"], maturity),
        "par_rate_percent": par * 100 if par is not None else None,
    })


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
        try:
            with session_scope() as session:
                terms = checked_terms(session, body.get("asset_class"), body["terms"])
        except ValueError as error:
            log.warning("price_preview_rejected", symbol=symbol,
                        asset_class=body.get("asset_class"), reason=str(error))
            return json_error(str(error), 400, symbol=symbol)
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
        instrument.model, inputs.get("curve"), getattr(instrument, "maturity_years", None),
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
    return hub.subscribe()


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
        try:
            with session_scope() as session:
                terms = checked_terms(
                    session, req.instrument.asset_class, req.instrument.as_terms(),
                )
        except ValueError as error:
            return json_error(str(error), 400)
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
