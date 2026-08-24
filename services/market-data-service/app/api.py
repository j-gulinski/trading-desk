import queue
import threading

import bottle
from bottle import request, response

from app import persistence, reference_set, scheduler, symbol_search, watchlist
from app.curve_feed import wire_curve
from app.publisher import (
    client_event_queues,
    clients_lock,
    last_event_id,
    publish_removal,
    stream_id,
)
from app.config import SERVICE_NAME
from shared import fx
from shared.active_set import load_active_set
from shared.freshness import classify
from shared.functions import utcnow
from shared.serialization import to_json
from shared.logging_config import get_logger

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


def _board_payload():
    active = load_active_set()
    reference = reference_set.reference_board_symbols()
    rows = []
    for row in persistence.board_rows():
        provider, symbol = row["provider"], row["symbol"]
        if provider in reference:
            if symbol not in reference[provider]:
                continue
            origin = {"watched": False, "held": False, "benchmark": False,
                      "reference": True}
        else:
            entry = active.get(symbol)
            if entry is None or not entry.serves(provider):
                continue
            origin = {**entry.origin(provider), "reference": False}
        row["event_time"] = row["received_at"]
        row.update(origin)
        rows.append(row)
    return rows


def _classify_row(row, now):
    return classify(
        True,
        row["provider_timestamp"],
        row["received_at"],
        now,
        row["stale_after_seconds"],
        market_open=row["market_open"],
        closed_stale_after_seconds=row["closed_stale_after_seconds"],
    )


def _quote_rows():
    now = utcnow()
    rows = _board_payload()
    for row in rows:
        row["freshness"] = _classify_row(row, now)
    return rows


@app.route("/snapshot")
@app.route("/market-data/snapshot")
def get_snapshot():
    response.content_type = "application/json"
    rows = _board_payload()
    curves = persistence.latest_curve_sets()
    return to_json({
        "stream_id": stream_id,
        "event_id": last_event_id() or None,
        "spots": {f"{row['provider']}:{row['symbol']}": row for row in rows},
        "curves": {entry["curve_name"]: wire_curve(entry) for entry in curves},
    })


@app.route("/curves")
@app.route("/market-data/curves")
def get_curves():
    response.content_type = "application/json"
    include_raw = (request.query.raw or "").strip() in ("1", "true")
    curves = persistence.latest_curve_sets(include_raw=include_raw)
    return to_json([wire_curve(entry) for entry in curves])


@app.route("/curves/<provider>")
@app.route("/market-data/curves/<provider>")
def get_provider_curves(provider):
    response.content_type = "application/json"
    normalized = provider.strip().upper()
    if normalized not in scheduler.wired_providers():
        response.status = 404
        return to_json({"error": f"unknown or unwired provider: {normalized}"})
    include_raw = (request.query.raw or "").strip() in ("1", "true")
    curves = persistence.latest_curve_sets(provider=normalized, include_raw=include_raw)
    return to_json([wire_curve(entry) for entry in curves])


@app.route("/curves/refresh", method="POST")
@app.route("/market-data/curves/refresh", method="POST")
def refresh_curves():
    response.content_type = "application/json"
    curve = (request.query.curve or "").strip().upper() or None
    provider = (request.query.provider or "").strip().upper() or None
    if curve is not None:
        entry, error, status = scheduler.refresh_curve(curve, provider)
        if error is not None:
            response.status = status
            log.warning("manual_curve_refresh_rejected", curve=curve,
                        provider=provider, reason=error)
            return to_json({"error": error, "curve": curve})
        log.info("manual_curve_refresh", curve=curve, provider=provider)
        return to_json(wire_curve(entry))
    refreshed, skipped = scheduler.refresh_curves(provider)
    log.info("manual_curve_refresh_all", provider=provider,
             refreshed=len(refreshed), skipped=skipped)
    return to_json({"refreshed": refreshed, "skipped": skipped})


@app.route("/quotes")
@app.route("/market-data/quotes")
def get_quotes():
    response.content_type = "application/json"
    symbol = (request.query.symbol or "").strip().upper() or None
    asset_class = (request.query.asset_class or "").strip().upper() or None
    provider = (request.query.provider or "").strip().upper() or None
    rows = [
        row for row in _quote_rows()
        if (symbol is None or row["symbol"] == symbol)
        and (asset_class is None or row["asset_class"] == asset_class)
        and (provider is None or row["provider"] == provider)
    ]
    return to_json(rows)


@app.route("/quotes/<provider>/<symbol>")
@app.route("/market-data/quotes/<provider>/<symbol>")
def get_quote(provider, symbol):
    response.content_type = "application/json"
    normalized_provider = provider.strip().upper()
    normalized_symbol = symbol.strip().upper()
    if normalized_provider not in scheduler.wired_providers():
        response.status = 404
        return to_json({
            "error": f"unknown or unwired provider: {normalized_provider}"
        })
    row = next(
        (
            item for item in _quote_rows()
            if item["provider"] == normalized_provider
            and item["symbol"] == normalized_symbol
        ),
        None,
    )
    if row is None:
        response.status = 404
        return to_json({
            "error": f"no active quote for {normalized_provider}:{normalized_symbol}"
        })
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
    if normalized_provider not in scheduler.wired_providers():
        response.status = 404
        return to_json({"error": f"unknown or unwired provider: {normalized_provider}"})
    include_raw = (request.query.raw or "").strip() in ("1", "true")
    return to_json(persistence.quote_history(
        normalized_provider, normalized_symbol, limit, include_raw
    ))


@app.route("/watchlist")
def get_watchlist():
    response.content_type = "application/json"
    return to_json(watchlist.list_items(scheduler.wired_quote_providers()))


def _refresh_added_feeds(symbol, providers):
    for provider in providers:
        _, error, _ = scheduler.refresh_symbol(symbol, provider)
        log.info("watchlist_add_refresh", symbol=symbol, provider=provider,
                 outcome="ok" if error is None else error)


@app.route("/watchlist", method="POST")
def post_watchlist():
    response.content_type = "application/json"
    body = dict(request.json or {})
    item, error, status = watchlist.add_item(
        body.get("symbol"), body.get("asset_class"), body.get("currency"),
        scheduler.wired_quote_providers(), body.get("providers"),
    )
    if error is not None:
        response.status = status
        return to_json({"error": error})
    scheduler.reload_active_set()
    threading.Thread(
        target=_refresh_added_feeds,
        args=(item["symbol"], item["added_providers"]),
        daemon=True,
    ).start()
    log.info("watchlist_symbol_added", symbol=item["symbol"],
             asset_class=item["asset_class"],
             providers=[p for p, on in item["providers"].items() if on])
    response.status = status
    return to_json(item)


@app.route("/watchlist/<symbol>", method="DELETE")
def delete_watchlist(symbol):
    response.content_type = "application/json"
    provider = (request.query.provider or "").strip().upper() or None
    result, error, status = watchlist.remove_item(symbol, provider)
    if error is not None:
        response.status = status
        return to_json({"error": error})
    scheduler.reload_active_set()
    normalized = symbol.strip().upper()
    active = load_active_set().get(normalized)
    released = [
        name for name in result["dropped"]
        if active is None or not active.serves(name)
    ]
    if released:
        persistence.delete_board_rows(normalized, released)
        publish_removal([{"provider": name, "symbol": normalized} for name in released])
    log.info("watchlist_symbol_removed", symbol=normalized, provider=provider,
             released=released, remaining=result["remaining"])
    return to_json({
        "symbol": normalized,
        "removed_providers": result["dropped"],
        "remaining_providers": result["remaining"],
        "still_polled": [name for name in result["dropped"] if name not in released],
    })


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
    return to_json({"query": query.upper(), "results": symbol_search.search(query)})


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
    if not symbol:
        refreshed, skipped = scheduler.refresh_all(provider)
        log.info("manual_refresh_all", provider=provider, refreshed=len(refreshed),
                 skipped=skipped)
        return to_json({"refreshed": refreshed, "skipped": skipped})
    tick, error, status = scheduler.refresh_symbol(symbol, provider)
    if error is not None:
        response.status = status
        log.warning("manual_refresh_rejected", symbol=symbol, provider=provider,
                    reason=error)
        return to_json({"error": error, "symbol": symbol})
    log.info("manual_refresh", symbol=symbol, provider=provider)
    return to_json(tick)
