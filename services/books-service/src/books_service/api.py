import uuid

import bottle
from bottle import request

from books_service.repository import DuplicateBookName
from books_service import repository
from desk_domain.instruments import INSTRUMENT_TYPES
from desk_runtime.http import json_error, json_response

app = bottle.Bottle()

ASSET_CLASS_FIELD = "expected_asset_class"


def _book_id(value):
    try:
        return str(uuid.UUID(value))
    except (AttributeError, TypeError, ValueError):
        return None


def _body():
    raw = request.json
    if raw is None:
        return {}, None
    if not isinstance(raw, dict):
        return None, "request body must be an object"
    return raw, None


def _identity_error(body, *, required):
    for field in ("name", ASSET_CLASS_FIELD):
        if field not in body:
            if required:
                return f"{field} is required"
            continue
        value = body[field]
        if not isinstance(value, str) or not value.strip():
            return f"{field} must be a non-empty string"
    asset_class = body.get(ASSET_CLASS_FIELD)
    if asset_class is not None and asset_class.strip().upper() not in INSTRUMENT_TYPES:
        return f"{ASSET_CLASS_FIELD} must be one of {', '.join(sorted(INSTRUMENT_TYPES))}"
    return None


def _deactivation_refusal(book_id):
    open_trades = repository.active_trade_count(book_id)
    if open_trades > 0:
        return json_error(
            "book has open trades", 409, book_id=book_id, active_trades=open_trades,
        )
    return None


@app.route("/books", method="GET")
def list_books():
    return json_response(repository.list_books())


@app.route("/books/<book_id>", method="GET")
def get_book(book_id):
    normalized = _book_id(book_id)
    book = repository.get_book(normalized) if normalized else None
    if book is None:
        return json_error("book not found", 404, book_id=book_id)
    return json_response(book)


@app.route("/books", method="POST")
def create_book():
    body, error = _body()
    if error is None:
        error = _identity_error(body, required=True)
    if error is not None:
        return json_error(error, 400)
    try:
        return json_response(repository.create_book(body), 201)
    except DuplicateBookName as taken:
        return json_error("a book with this name already exists", 409, name=str(taken))


@app.route("/books/<book_id>", method="PUT")
def update_book(book_id):
    normalized = _book_id(book_id)
    if normalized is None:
        return json_error("book not found", 404, book_id=book_id)
    body, error = _body()
    if error is None:
        error = _identity_error(body, required=False)
    if error is not None:
        return json_error(error, 400)
    if body.get("is_active") is False:
        refusal = _deactivation_refusal(normalized)
        if refusal is not None:
            return refusal
    try:
        updated = repository.update_book(normalized, body)
    except DuplicateBookName as taken:
        return json_error("a book with this name already exists", 409, name=str(taken))
    if updated is None:
        return json_error("book not found", 404, book_id=book_id)
    return json_response(updated)


@app.route("/books/<book_id>", method="DELETE")
def delete_book(book_id):
    normalized = _book_id(book_id)
    if normalized is None or repository.get_book(normalized) is None:
        return json_error("book not found", 404, book_id=book_id)
    refusal = _deactivation_refusal(normalized)
    if refusal is not None:
        return refusal
    return json_response(repository.deactivate_book(normalized))
