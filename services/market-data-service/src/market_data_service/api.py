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
from desk_runtime.http import json_error, json_response, query_flag, query_text, query_upper
from desk_runtime.serialization import to_json
from desk_runtime.logging_config import get_logger

log = get_logger(SERVICE_NAME)
app = bottle.Bottle()

QUOTE_HISTORY_DEFAULT_LIMIT = 60
QUOTE_HISTORY_MAX_LIMIT = 200


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
        return json_error(f"unknown or unwired provider: {provider}", 404)
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
def stream():
    return _serve_stream()


@app.route("/stream/<provider>")
def provider_stream(provider):
    return _serve_stream(provider.strip().upper())


@app.route("/snapshot")
def get_snapshot():
    # Every event at or below this watermark was persisted before it was published.
    checkpoint = last_event_id()
    rows = quote_service.board_rows()
    return json_response({
        "stream_id": stream_id,
        "event_id": checkpoint or None,
        "spots": {f"{row['provider']}:{row['symbol']}": row for row in rows},
        "curves": curve_service.snapshot_curves(),
    })


@app.route("/curves")
def get_curves():
    curves, _, _ = curve_service.list_curves(include_raw=query_flag("raw"))
    return json_response(curves)


@app.route("/curves/<provider>")
def get_provider_curves(provider):
    curves, error, status = curve_service.list_curves(
        provider.strip().upper(), query_flag("raw"),
    )
    if error is not None:
        return json_error(error, status)
    return json_response(curves)


@app.route("/curves/<provider>/<curve_name>/<as_of>")
def get_curve_revision(provider, curve_name, as_of):
    curve, error, status = curve_service.get_curve_revision(
        provider.strip().upper(),
        curve_name.strip().upper(),
        as_of.strip(),
        query_flag("raw"),
    )
    if error is not None:
        return json_error(error, status)
    return json_response(curve)


@app.route("/curves/refresh", method="POST")
def refresh_curves():
    curve = query_upper("curve")
    result, error, status = curve_service.refresh(curve, query_upper("provider"))
    if error is not None:
        return json_error(error, status, curve=curve)
    return json_response(result)


@app.route("/quotes")
def get_quotes():
    return json_response(quote_service.list_quotes(
        query_upper("symbol"), query_upper("asset_class"), query_upper("provider"),
    ))


@app.route("/quotes/<provider>/<symbol>")
def get_quote(provider, symbol):
    row, error, status = quote_service.get_quote(
        provider.strip().upper(), symbol.strip().upper(),
    )
    if error is not None:
        return json_error(error, status)
    return json_response(row)


@app.route("/quotes/<provider>/<symbol>/history")
def get_quote_history(provider, symbol):
    try:
        limit = int(query_text("limit", QUOTE_HISTORY_DEFAULT_LIMIT))
    except (TypeError, ValueError):
        return json_error(
            f"limit must be an integer between 1 and {QUOTE_HISTORY_MAX_LIMIT}", 400,
        )
    if not 1 <= limit <= QUOTE_HISTORY_MAX_LIMIT:
        return json_error(f"limit must be between 1 and {QUOTE_HISTORY_MAX_LIMIT}", 400)
    history, error, status = quote_service.get_quote_history(
        provider.strip().upper(), symbol.strip().upper(), limit, query_flag("raw"),
    )
    if error is not None:
        return json_error(error, status)
    return json_response(history)


@app.route("/watchlist")
def get_watchlist():
    return json_response(quote_service.list_watchlist())


@app.route("/watchlist", method="POST")
def post_watchlist():
    raw_body = request.json
    if not isinstance(raw_body, dict):
        return json_error("request body must be an object", 400)
    item, error, status = quote_service.add_watchlist_item(dict(raw_body))
    if error is not None:
        return json_error(error, status)
    return json_response(item, status)


@app.route("/watchlist/<symbol>", method="DELETE")
def delete_watchlist(symbol):
    result, error, status = quote_service.remove_watchlist_item(
        symbol, query_upper("provider"),
    )
    if error is not None:
        return json_error(error, status)
    return json_response(result)


@app.route("/fx/rates")
def get_fx_rates():
    to_currency = query_upper("to", "")
    if not watchlist.CURRENCY_PATTERN.match(to_currency):
        return json_error("to must be a 3-letter ISO currency code", 400)
    return json_response({"to": to_currency, "rates": fx.rates_to(to_currency)})


@app.route("/symbols/search")
def search_symbols():
    query = query_text("q", "")
    if len(query) < 2:
        return json_error("q must be at least 2 characters", 400)
    results, provider_errors = symbol_search.search(query)
    if len(provider_errors) == len(scheduler.wired_quote_providers()):
        return json_error(
            "symbol search is unavailable from every wired provider", 503,
            provider_errors=provider_errors,
        )
    return json_response({
        "query": query.upper(),
        "results": results,
        "provider_errors": provider_errors,
    })


@app.route("/providers")
def get_providers():
    return json_response(scheduler.providers_overview())


@app.route("/providers/<name>/health")
def get_provider_health(name):
    detail = scheduler.provider_health(name.strip().upper())
    if detail is None:
        return json_error(f"unknown provider: {name}", 404)
    return json_response(detail)


@app.route("/refresh", method="POST")
def refresh():
    symbol = query_upper("symbol")
    provider = query_upper("provider")
    tick, error, status = quote_service.refresh(symbol, provider)
    if error is not None:
        return json_error(error, status, symbol=symbol, provider=provider)
    return json_response(tick)
