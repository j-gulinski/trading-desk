# Variant B: FastAPI. Same contract as sample_wsgi; only the HTTP layer differs.
import hashlib
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Response

from books_service import repository
from desk_runtime.serialization import to_json

DOWNSTREAM = os.environ.get("DOWNSTREAM_URL", "http://127.0.0.1:9000/delay/50")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=5)
    yield
    await app.state.http.aclose()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/io")
async def io():
    r = await app.state.http.get(DOWNSTREAM)  # the event loop serves others meanwhile
    return {"downstream": r.json()}


@app.get("/cpu")
def cpu(n: int = 20000):  # def: computation would block the event loop, so it runs in the thread pool
    h = b"x"
    for _ in range(n):
        h = hashlib.sha256(h).digest()
    return {"digest": h.hex()[:16]}


# S4: the same repository call as books-service. def: the database driver is synchronous.
@app.get("/books")
def list_books():
    return Response(to_json(repository.list_books()), media_type="application/json")
