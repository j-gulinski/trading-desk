import bottle
import uuid
from bottle import request, response

from app import cache, service, repository
from app.config import SERVICE_NAME
from shared.serialization import to_json

app = bottle.Bottle()
MAX_TRADE_PAGE_SIZE = 500


def _json(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return to_json(data)


def _page():
    try:
        limit = int(request.query.get("limit") or 100)
        offset = int(request.query.get("offset") or 0)
    except (TypeError, ValueError):
        return None, "limit and offset must be integers"
    if not 1 <= limit <= MAX_TRADE_PAGE_SIZE:
        return None, f"limit must be between 1 and {MAX_TRADE_PAGE_SIZE}"
    if offset < 0:
        return None, "offset must be zero or greater"
    return (limit, offset), None


def _book_filter():
    raw = request.query.get("book_id") or None
    if raw is None:
        return None, None
    try:
        return str(uuid.UUID(raw)), None
    except (AttributeError, TypeError, ValueError):
        return None, "book_id must be a UUID"


def _trade_id(value):
    try:
        return str(uuid.UUID(value))
    except (AttributeError, TypeError, ValueError):
        return None


@app.route("/health")
def health():
    return _json({
        "service": SERVICE_NAME,
        "status": "UP",
        "cached_trades": len(cache.trades),
        "cached_valuations": len(cache.valuations),
    })


@app.route("/books/summary")
def books_summary():
    return _json(service.books_summary())


@app.route("/trades/overview")
def trades_overview():
    page, error = _page()
    if error is not None:
        return _json({"error": error}, 400)
    book_id, error = _book_filter()
    if error is not None:
        return _json({"error": error}, 400)
    limit, offset = page
    return _json({
        "trades": service.list_trades(
            book_id=book_id,
            asset_class=request.query.get("asset_class") or None,
            status=request.query.get("status") or None,
            symbol=request.query.get("symbol") or None,
            limit=limit,
            offset=offset,
        ),
        "books": service.books_summary(),
    })


@app.route("/trades")
def list_trades():
    page, error = _page()
    if error is not None:
        return _json({"error": error}, 400)
    book_id, error = _book_filter()
    if error is not None:
        return _json({"error": error}, 400)
    limit, offset = page
    return _json(service.list_trades(
        book_id=book_id,
        asset_class=request.query.get("asset_class") or None,
        status=request.query.get("status") or None,
        symbol=request.query.get("symbol") or None,
        limit=limit,
        offset=offset,
    ))


@app.route("/trades/<trade_id>")
def trade_detail(trade_id):
    normalized = _trade_id(trade_id)
    if normalized is None:
        return _json({"error": "trade not found", "trade_id": trade_id}, 404)
    detail = service.trade_detail(normalized)
    if detail is None:
        return _json({"error": "trade not found", "trade_id": trade_id}, 404)
    return _json(detail)


@app.route("/trades/<trade_id>/valuations")
def trade_valuations(trade_id):
    normalized = _trade_id(trade_id)
    if normalized is None:
        return _json({"error": "trade not found", "trade_id": trade_id}, 404)
    return _json(repository.valuation_history(normalized))


@app.route("/trades/<trade_id>/audit-logs")
def trade_audit_logs(trade_id):
    normalized = _trade_id(trade_id)
    if normalized is None:
        return _json({"error": "trade not found", "trade_id": trade_id}, 404)
    return _json(repository.audit_logs(normalized))
