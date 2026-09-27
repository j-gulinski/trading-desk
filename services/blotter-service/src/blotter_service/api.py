import bottle
import re
import uuid

from blotter_service import live_valuations, repository, service
from blotter_service.config import SERVICE_NAME
from desk_runtime.http import json_error, json_response, query_text, query_upper

app = bottle.Bottle()
MAX_TRADE_PAGE_SIZE = 500


def _page():
    try:
        limit = int(query_text("limit", 100))
        offset = int(query_text("offset", 0))
    except (TypeError, ValueError):
        return None, "limit and offset must be integers"
    if not 1 <= limit <= MAX_TRADE_PAGE_SIZE:
        return None, f"limit must be between 1 and {MAX_TRADE_PAGE_SIZE}"
    if offset < 0:
        return None, "offset must be zero or greater"
    return (limit, offset), None


def _book_filter():
    raw = query_text("book_id")
    if raw is None:
        return None, None
    try:
        return str(uuid.UUID(raw)), None
    except (AttributeError, TypeError, ValueError):
        return None, "book_id must be a UUID"


def _reporting_currency():
    currency = query_upper("currency")
    if currency is None or re.fullmatch(r"[A-Z]{3}", currency):
        return currency, None
    return None, "currency must be a 3-letter ISO currency code"


def _trade_id(value):
    try:
        return str(uuid.UUID(value))
    except (AttributeError, TypeError, ValueError):
        return None


def _trade_query():
    page, error = _page()
    if error is not None:
        return None, error
    book_id, error = _book_filter()
    if error is not None:
        return None, error
    limit, offset = page
    return {
        "book_id": book_id,
        "asset_class": query_text("asset_class"),
        "status": query_text("status"),
        "symbol": query_text("symbol"),
        "limit": limit,
        "offset": offset,
    }, None


@app.route("/health")
def health():
    return json_response({
        "service": SERVICE_NAME,
        "status": "UP",
        "live_valuations": live_valuations.count(),
    })


@app.route("/books/summary")
def books_summary():
    currency, error = _reporting_currency()
    if error is not None:
        return json_error(error, 400)
    return json_response(service.books_summary(currency))


@app.route("/trades/overview")
def trades_overview():
    query, error = _trade_query()
    if error is not None:
        return json_error(error, 400)
    return json_response({
        "trades": service.list_trades(**query),
        "books": service.books_summary()["books"],
    })


@app.route("/trades")
def list_trades():
    query, error = _trade_query()
    if error is not None:
        return json_error(error, 400)
    return json_response(service.list_trades(**query))


@app.route("/trades/<trade_id>")
def trade_detail(trade_id):
    normalized = _trade_id(trade_id)
    if normalized is None:
        return json_error("trade not found", 404, trade_id=trade_id)
    detail = service.trade_detail(normalized)
    if detail is None:
        return json_error("trade not found", 404, trade_id=trade_id)
    return json_response(detail)


@app.route("/trades/<trade_id>/valuations")
def trade_valuations(trade_id):
    normalized = _trade_id(trade_id)
    if normalized is None:
        return json_error("trade not found", 404, trade_id=trade_id)
    return json_response(repository.valuation_history(normalized))


@app.route("/trades/<trade_id>/audit-logs")
def trade_audit_logs(trade_id):
    normalized = _trade_id(trade_id)
    if normalized is None:
        return json_error("trade not found", 404, trade_id=trade_id)
    return json_response(repository.audit_logs(normalized))
