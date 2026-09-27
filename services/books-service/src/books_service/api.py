import uuid

import bottle
from bottle import request

from books_service.repository import BookConflict
from books_service import repository
from desk_domain.instruments import INSTRUMENT_TYPES
from desk_runtime.http import json_error, json_response

app = bottle.Bottle()

ASSET_CLASS_FIELD = "expected_asset_class"
NAME_MAX_LENGTH = 60
DESCRIPTION_MAX_LENGTH = 200


def _book_id(value):
    try:
        return str(uuid.UUID(value))
    except (AttributeError, TypeError, ValueError):
        return None


def _text(body, field, max_length=None):
    value = body[field]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    value = value.strip()
    if max_length is not None and len(value) > max_length:
        raise ValueError(f"{field} must be at most {max_length} characters")
    return value


def _book_fields(*, creating):
    body = request.json
    if body is None:
        body = {}
    if not isinstance(body, dict):
        raise ValueError("request body must be an object")
    fields = {}
    for field in ("name", ASSET_CLASS_FIELD):
        if field in body:
            fields[field] = _text(body, field, NAME_MAX_LENGTH if field == "name" else None)
        elif creating:
            raise ValueError(f"{field} is required")
    if ASSET_CLASS_FIELD in fields:
        fields[ASSET_CLASS_FIELD] = fields[ASSET_CLASS_FIELD].upper()
        if fields[ASSET_CLASS_FIELD] not in INSTRUMENT_TYPES:
            raise ValueError(
                f"{ASSET_CLASS_FIELD} must be one of {', '.join(sorted(INSTRUMENT_TYPES))}"
            )
    if body.get("description") not in (None, ""):
        fields["description"] = _text(body, "description", DESCRIPTION_MAX_LENGTH)
    elif "description" in body:
        fields["description"] = None
    return fields


def _conflict(conflict):
    return json_error(str(conflict), 409, **conflict.fields)


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
    try:
        fields = _book_fields(creating=True)
    except ValueError as error:
        return json_error(str(error), 400)
    try:
        return json_response(repository.create_book(fields), 201)
    except BookConflict as conflict:
        return _conflict(conflict)


@app.route("/books/<book_id>", method="PUT")
def update_book(book_id):
    normalized = _book_id(book_id)
    if normalized is None:
        return json_error("book not found", 404, book_id=book_id)
    try:
        fields = _book_fields(creating=False)
    except ValueError as error:
        return json_error(str(error), 400)
    try:
        updated = repository.update_book(normalized, fields)
    except BookConflict as conflict:
        return _conflict(conflict)
    if updated is None:
        return json_error("book not found", 404, book_id=book_id)
    return json_response(updated)


@app.route("/books/<book_id>", method="DELETE")
def delete_book(book_id):
    normalized = _book_id(book_id)
    try:
        deactivated = repository.deactivate_book(normalized) if normalized else None
    except BookConflict as conflict:
        return _conflict(conflict)
    if deactivated is None:
        return json_error("book not found", 404, book_id=book_id)
    return json_response(deactivated)
