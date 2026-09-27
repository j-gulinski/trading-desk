import bottle
from bottle import request, response

from market_data_service import (
    curve_service, feeds, quote_board, quote_service, symbol_search, watchlist,
)
from market_data_service.publisher import hub, last_event_id, stream_id
from desk_domain import fx
from desk_runtime.http import json_error, json_response, query_flag, query_text, query_upper

app = bottle.Bottle()

QUOTE_HISTORY_DEFAULT_LIMIT = 60
QUOTE_HISTORY_MAX_LIMIT = 200


@app.route("/stream")
def stream():
    response.content_type = "text/event-stream"
    response.set_header("Cache-Control", "no-cache")
    return hub.subscribe()


@app.route("/snapshot")
def get_snapshot():
    checkpoint = last_event_id()
    rows = quote_board.board_rows()
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
    return json_response({
        "query": query.upper(),
        "results": results,
        "provider_errors": provider_errors,
    })


@app.route("/providers")
def get_providers():
    return json_response(feeds.providers_overview())


@app.route("/refresh", method="POST")
def refresh():
    symbol = query_upper("symbol")
    provider = query_upper("provider")
    tick, error, status = quote_service.refresh(symbol, provider)
    if error is not None:
        return json_error(error, status, symbol=symbol, provider=provider)
    return json_response(tick)
