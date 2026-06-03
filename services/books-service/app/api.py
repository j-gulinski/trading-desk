import bottle
from bottle import request, response

from app import repository
from app.config import SERVICE_NAME
from shared.serialization import to_json

app = bottle.Bottle()


def _json(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return to_json(data)


@app.route("/health")
def health():
    return _json({"service": SERVICE_NAME, "status": "UP"})


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
    return _json(repository.update_book(book_id, request.json or {}))


@app.route("/books/<book_id>", method="DELETE")
def delete_book(book_id):
    return _json(repository.deactivate_book(book_id))
