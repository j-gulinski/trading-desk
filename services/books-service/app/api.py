import bottle
from bottle import request, response

from app import blotter_client, repository
from app.blotter_client import BlotterUnavailable
from app.config import SERVICE_NAME
from shared.serialization import to_json

app = bottle.Bottle()


def _json(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return to_json(data)


def _deactivation_refusal(book_id):
    try:
        open_trades = blotter_client.active_trade_count(book_id)
    except BlotterUnavailable:
        return _json({
            "error": "open trades could not be verified",
            "book_id": book_id,
        }, 503)
    if open_trades > 0:
        return _json({
            "error": "book has open trades",
            "book_id": book_id,
            "active_trades": open_trades,
        }, 409)
    return None


@app.route("/books", method="GET")
def list_books():
    return _json(repository.list_books())


@app.route("/books/<book_id>", method="GET")
def get_book(book_id):
    return _json(repository.get_book(book_id))


@app.route("/books", method="POST")
def create_book():
    return _json(repository.create_book(request.json or {}), 201)


@app.route("/books/<book_id>", method="PUT")
def update_book(book_id):
    body = request.json or {}
    if body.get("is_active") is False:
        refusal = _deactivation_refusal(book_id)
        if refusal is not None:
            return refusal
    return _json(repository.update_book(book_id, body))


@app.route("/books/<book_id>", method="DELETE")
def delete_book(book_id):
    if repository.get_book(book_id) is None:
        return _json({"error": "book not found", "book_id": book_id}, 404)
    refusal = _deactivation_refusal(book_id)
    if refusal is not None:
        return refusal
    return _json(repository.deactivate_book(book_id))
