import bottle
from bottle import request, response

from app import cache, service, repository
from app.config import SERVICE_NAME
from shared.serialization import to_json

app = bottle.Bottle()


def _json(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return to_json(data)


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
    return _json({
        "trades": service.list_trades(
            book_id=request.query.get("book_id") or None,
            asset_class=request.query.get("asset_class") or None,
            status=request.query.get("status") or None,
            symbol=request.query.get("symbol") or None,
            limit=int(request.query.get("limit") or 100),
            offset=int(request.query.get("offset") or 0),
        ),
        "books": service.books_summary(),
    })


@app.route("/trades")
def list_trades():
    return _json(service.list_trades(
        book_id=request.query.get("book_id") or None,
        asset_class=request.query.get("asset_class") or None,
        status=request.query.get("status") or None,
        symbol=request.query.get("symbol") or None,
        limit=int(request.query.get("limit") or 100),
        offset=int(request.query.get("offset") or 0),
    ))


@app.route("/trades/<trade_id>")
def trade_detail(trade_id):
    detail = service.trade_detail(trade_id)
    if detail is None:
        return _json({"error": "trade not found", "trade_id": trade_id}, 404)
    return _json(detail)


@app.route("/trades/<trade_id>/valuations")
def trade_valuations(trade_id):
    return _json(repository.valuation_history(trade_id))


@app.route("/trades/<trade_id>/audit-logs")
def trade_audit_logs(trade_id):
    return _json(repository.audit_logs(trade_id))
