import queue

import bottle
from bottle import request, response

from market_data_service import curve_service, quote_service, scheduler, symbol_search, watchlist
from market_data_service.publisher import (
    client_event_queues,
    clients_lock,
    last_event_id,
    STREAM_OVERFLOW,
    stream_id,
)
from market_data_service.config import SERVICE_NAME
from desk_domain import fx
from desk_runtime.serialization import to_json
from desk_runtime.logging_config import get_logger

log = get_logger(SERVICE_NAME)
app = bottle.Bottle()


def _provider_event(message, provider):
    if provider is None:
        return message
    data = message["data"]
    if data.get("provider") == provider:
        return message
    rows = data.get("rows")
    if not isinstance(rows, list):
        return None
    matching = [row for row in rows if row.get("provider") == provider]
    if not matching:
        return None
    return {**message, "data": {**data, "rows": matching}}


def _serve_stream(provider=None):
    if provider is not None and provider not in scheduler.wired_providers():
        response.status = 404
        response.content_type = "application/json"
        return to_json({"error": f"unknown or unwired provider: {provider}"})
    response.content_type = "text/event-stream"
    response.set_header("Cache-Control", "no-cache")
    with clients_lock:
        client_q = queue.Queue(maxsize=500)
        client_event_queues.add(client_q)
    log.info("stream_client_connected", provider=provider)

    def generate_events():
        yield ": connected\n\n"
        try:
            while True:
                message = client_q.get()
                if message is STREAM_OVERFLOW:
                    log.warning("stream_client_disconnected_after_overflow", provider=provider)
                    return
                selected = _provider_event(message, provider)
                if selected is not None:
                    yield (
                        f"event: {selected['event']}\n"
                        f"data: {to_json(selected['data'])}\n\n"
                    )
        except Exception as exc:
            log.debug("stream_client_error", error=type(exc).__name__)
        finally:
            with clients_lock:
                client_event_queues.discard(client_q)
            log.info("stream_client_disconnected", provider=provider)

    return generate_events()


@app.route("/stream")
@app.route("/market-data/stream")
def stream():
    return _serve_stream()


@app.route("/stream/<provider>")
@app.route("/market-data/stream/<provider>")
def provider_stream(provider):
    return _serve_stream(provider.strip().upper())


@app.route("/snapshot")
@app.route("/market-data/snapshot")
def get_snapshot():
    response.content_type = "application/json"
    # Every event at or below this watermark was persisted before it was published.
    checkpoint = last_event_id()
    rows = quote_service.board_rows()
    return to_json({
        "stream_id": stream_id,
        "event_id": checkpoint or None,
        "spots": {f"{row['provider']}:{row['symbol']}": row for row in rows},
        "curves": curve_service.snapshot_curves(),
    })


@app.route("/curves")
@app.route("/market-data/curves")
def get_curves():
    response.content_type = "application/json"
    include_raw = (request.query.raw or "").strip() in ("1", "true")
    curves, _, _ = curve_service.list_curves(include_raw=include_raw)
    return to_json(curves)


@app.route("/curves/<provider>")
@app.route("/market-data/curves/<provider>")
def get_provider_curves(provider):
    response.content_type = "application/json"
    normalized = provider.strip().upper()
    include_raw = (request.query.raw or "").strip() in ("1", "true")
    curves, error, status = curve_service.list_curves(normalized, include_raw)
    if error is not None:
        response.status = status
        return to_json({"error": error})
    return to_json(curves)


@app.route("/curves/<provider>/<curve_name>/<as_of>")
@app.route("/market-data/curves/<provider>/<curve_name>/<as_of>")
def get_curve_revision(provider, curve_name, as_of):
    response.content_type = "application/json"
    normalized_provider = provider.strip().upper()
    normalized_curve = curve_name.strip().upper()
    include_raw = (request.query.raw or "").strip() in ("1", "true")
    curve, error, status = curve_service.get_curve_revision(
        normalized_provider,
        normalized_curve,
        as_of.strip(),
        include_raw,
    )
    if error is not None:
        response.status = status
        return to_json({"error": error})
    return to_json(curve)


@app.route("/curves/refresh", method="POST")
@app.route("/market-data/curves/refresh", method="POST")
def refresh_curves():
    response.content_type = "application/json"
    curve = (request.query.curve or "").strip().upper() or None
    provider = (request.query.provider or "").strip().upper() or None
    result, error, status = curve_service.refresh(curve, provider)
    if error is not None:
        response.status = status
        return to_json({"error": error, "curve": curve})
    return to_json(result)


@app.route("/quotes")
@app.route("/market-data/quotes")
def get_quotes():
    response.content_type = "application/json"
    symbol = (request.query.symbol or "").strip().upper() or None
    asset_class = (request.query.asset_class or "").strip().upper() or None
    provider = (request.query.provider or "").strip().upper() or None
    return to_json(quote_service.list_quotes(symbol, asset_class, provider))


@app.route("/quotes/<provider>/<symbol>")
@app.route("/market-data/quotes/<provider>/<symbol>")
def get_quote(provider, symbol):
    response.content_type = "application/json"
    normalized_provider = provider.strip().upper()
    normalized_symbol = symbol.strip().upper()
    row, error, status = quote_service.get_quote(
        normalized_provider, normalized_symbol
    )
    if error is not None:
        response.status = status
        return to_json({"error": error})
    return to_json(row)


@app.route("/quotes/<provider>/<symbol>/history")
@app.route("/market-data/quotes/<provider>/<symbol>/history")
def get_quote_history(provider, symbol):
    response.content_type = "application/json"
    normalized_provider = provider.strip().upper()
    normalized_symbol = symbol.strip().upper()
    try:
        limit = int(request.query.limit or 60)
    except (TypeError, ValueError):
        response.status = 400
        return to_json({"error": "limit must be an integer between 1 and 200"})
    if not 1 <= limit <= 200:
        response.status = 400
        return to_json({"error": "limit must be between 1 and 200"})
    include_raw = (request.query.raw or "").strip() in ("1", "true")
    history, error, status = quote_service.get_quote_history(
        normalized_provider, normalized_symbol, limit, include_raw
    )
    if error is not None:
        response.status = status
        return to_json({"error": error})
    return to_json(history)


@app.route("/watchlist")
def get_watchlist():
    response.content_type = "application/json"
    return to_json(quote_service.list_watchlist())


@app.route("/watchlist", method="POST")
def post_watchlist():
    response.content_type = "application/json"
    raw_body = request.json
    if not isinstance(raw_body, dict):
        response.status = 400
        return to_json({"error": "request body must be an object"})
    body = dict(raw_body)
    item, error, status = quote_service.add_watchlist_item(body)
    if error is not None:
        response.status = status
        return to_json({"error": error})
    response.status = status
    return to_json(item)


@app.route("/watchlist/<symbol>", method="DELETE")
def delete_watchlist(symbol):
    response.content_type = "application/json"
    provider = (request.query.provider or "").strip().upper() or None
    result, error, status = quote_service.remove_watchlist_item(symbol, provider)
    if error is not None:
        response.status = status
        return to_json({"error": error})
    return to_json(result)


@app.route("/fx/rates")
def get_fx_rates():
    response.content_type = "application/json"
    to_currency = (request.query.to or "").strip().upper()
    if not watchlist.CURRENCY_PATTERN.match(to_currency):
        response.status = 400
        return to_json({"error": "to must be a 3-letter ISO currency code"})
    return to_json({"to": to_currency, "rates": fx.rates_to(to_currency)})


@app.route("/symbols/search")
def search_symbols():
    response.content_type = "application/json"
    query = (request.query.q or "").strip()
    if len(query) < 2:
        response.status = 400
        return to_json({"error": "q must be at least 2 characters"})
    results, provider_errors = symbol_search.search(query)
    if len(provider_errors) == len(scheduler.wired_quote_providers()):
        response.status = 503
        return to_json({
            "error": "symbol search is unavailable from every wired provider",
            "provider_errors": provider_errors,
        })
    return to_json({
        "query": query.upper(),
        "results": results,
        "provider_errors": provider_errors,
    })


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
@app.route("/market-data/refresh", method="POST")
def refresh():
    response.content_type = "application/json"
    symbol = (request.query.symbol or "").strip().upper()
    provider = (request.query.provider or "").strip().upper() or None
    tick, error, status = quote_service.refresh(symbol or None, provider)
    if error is not None:
        response.status = status
        return to_json({"error": error, "symbol": symbol, "provider": provider})
    return to_json(tick)
