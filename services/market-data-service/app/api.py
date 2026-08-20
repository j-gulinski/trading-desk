import queue
import bottle
from bottle import request, response

from app import persistence, scheduler, symbol_search, watchlist
from app.publisher import (
    client_event_queues,
    clients_lock,
    last_event_id,
    publish_removal,
    stream_id,
)
from app.config import (
    HISTORY_MAX_POINTS,
    SERVICE_NAME,
    TODAY_HISTORY_BUCKET_SECONDS,
)
from shared.active_set import load_active_set
from shared.freshness import classify
from shared.functions import utcnow
from shared.providers import supports_quotes
from shared.serialization import to_json
from shared.logging_config import get_logger

log = get_logger(SERVICE_NAME)
app = bottle.Bottle()


def route(*paths, **kwargs):
    def decorate(handler):
        for path in paths:
            app.route(path, **kwargs)(handler)
        return handler
    return decorate


@route("/stream", "/market-data/stream")
def stream():
    response.content_type = "text/event-stream"
    response.set_header("Cache-Control", "no-cache")
    with clients_lock:
        client_q = queue.Queue(maxsize=500)
        client_event_queues.add(client_q)
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
            with clients_lock:
                client_event_queues.discard(client_q)
            log.info("stream_client_disconnected")

    return generate_events()


@route("/stream/<provider>", "/market-data/stream/<provider>")
def provider_stream(provider):
    provider = provider.upper()
    response.content_type = "text/event-stream"
    response.set_header("Cache-Control", "no-cache")
    with clients_lock:
        client_q = queue.Queue(maxsize=500)
        client_event_queues.add(client_q)
    log.info("stream_client_connected", provider=provider)

    def matches(message):
        data = message["data"]
        if message["event"] == "market_remove":
            return any(row["provider"] == provider for row in data.get("rows", []))
        return data.get("provider") == provider

    def generate_events():
        yield ": connected\n\n"
        try:
            while True:
                message = client_q.get()
                if not matches(message):
                    continue
                data = message["data"]
                if message["event"] == "market_remove":
                    data = {
                        **data,
                        "rows": [row for row in data.get("rows", [])
                                 if row["provider"] == provider],
                    }
                yield f"event: {message['event']}\ndata: {to_json(data)}\n\n"
        except Exception as exc:
            log.debug("stream_client_error", error=type(exc).__name__)
        finally:
            with clients_lock:
                client_event_queues.discard(client_q)
            log.info("stream_client_disconnected", provider=provider)

    return generate_events()


def _board_payload():
    active = load_active_set()
    rows = [
        row for row in persistence.board_rows()
        if row["symbol"] in active and active[row["symbol"]].serves(row["provider"])
    ]
    for row in rows:
        row["event_time"] = row["received_at"]
        row.update(active[row["symbol"]].origin(row["provider"]))
    return rows


def _classify_row(row, now, supported=True):
    return classify(
        supported,
        row["provider_timestamp"],
        row["received_at"],
        now,
        row["stale_after_seconds"],
        market_open=row["market_open"],
        closed_stale_after_seconds=row["closed_stale_after_seconds"],
    )


def _placeholder_row(provider, symbol, entry):
    return {
        "provider": provider,
        "symbol": symbol,
        "asset_class": entry.asset_class,
        "currency": entry.currency,
        "bid": None,
        "ask": None,
        "last": None,
        "mid": None,
        "price_basis": None,
        "quote_grade": None,
        "previous_close": None,
        "provider_timestamp": None,
        "received_at": None,
        "event_time": None,
        "latest_snapshot_id": None,
        "market_open": scheduler.market_open(provider, symbol),
        "stale_after_seconds": scheduler.stale_after_seconds(provider, symbol),
        "closed_stale_after_seconds": scheduler.closed_stale_after_seconds(provider, symbol),
        **entry.origin(provider),
    }


def _quote_rows():
    now = utcnow()
    rows = _board_payload()
    for row in rows:
        row["freshness"] = _classify_row(row, now)
    have = {(row["provider"], row["symbol"]) for row in rows}
    for symbol, entry in load_active_set().items():
        for provider in scheduler.wired_quote_providers():
            if (provider, symbol) in have:
                continue
            supported = supports_quotes(provider, entry.asset_class)
            if supported and not entry.serves(provider):
                continue
            row = _placeholder_row(provider, symbol, entry)
            row["freshness"] = _classify_row(row, now, supported=supported)
            rows.append(row)
    return rows


@route("/snapshot", "/market-data/snapshot")
def get_snapshot():
    response.content_type = "application/json"
    rows = _board_payload()
    return to_json({
        "stream_id": stream_id,
        "event_id": last_event_id() or None,
        "spots": {f"{row['provider']}:{row['symbol']}": row for row in rows},
        "curves": {},
    })


@route("/quotes", "/market-data/quotes")
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


@route("/quotes/<provider>/<symbol>", "/market-data/quotes/<provider>/<symbol>")
def get_quote(provider, symbol):
    response.content_type = "application/json"
    provider, symbol = provider.upper(), symbol.upper()
    for row in _quote_rows():
        if row["provider"] == provider and row["symbol"] == symbol:
            return to_json(row)
    response.status = 404
    return to_json({"error": f"{provider} does not quote {symbol}"})


@app.route("/watchlist")
def get_watchlist():
    response.content_type = "application/json"
    return to_json(watchlist.list_items(scheduler.wired_quote_providers()))


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


@app.route("/symbols/search")
def search_symbols():
    response.content_type = "application/json"
    query = (request.query.q or "").strip()
    if len(query) < 2:
        response.status = 400
        return to_json({"error": "q must be at least 2 characters"})
    return to_json({"query": query.upper(), "results": symbol_search.search(query)})


@route("/history", "/market-data/history")
def get_history():
    response.content_type = "application/json"
    return to_json({
        "session": "TODAY",
        "bucket_seconds": TODAY_HISTORY_BUCKET_SECONDS,
        "series": persistence.today_history_series(
            TODAY_HISTORY_BUCKET_SECONDS, HISTORY_MAX_POINTS
        ),
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


@route("/refresh", "/market-data/refresh", method="POST")
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
