# Variants A and A-threads: Bottle. Same contract as sample_asgi; only the HTTP layer differs.
import hashlib
import os

import requests
from bottle import Bottle, request

from books_service.api import app as books_app

DOWNSTREAM = os.environ.get("DOWNSTREAM_URL", "http://127.0.0.1:9000/delay/50")

app = Bottle()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/io")
def io():
    r = requests.get(DOWNSTREAM, timeout=5)  # the worker thread waits here
    return {"downstream": r.json()}


@app.get("/cpu")
def cpu():
    n = int(request.query.get("n", 20000))
    h = b"x"
    for _ in range(n):
        h = hashlib.sha256(h).digest()
    return {"digest": h.hex()[:16]}


# S4: the real books-service routes and handlers, unchanged.
app.merge(books_app)
