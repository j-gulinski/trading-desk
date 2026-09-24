import hashlib
import uuid

import requests
from requests.adapters import HTTPAdapter

from books_service import repository
from desk_runtime.logging_config import configure_logging

STUB_URL = "http://stub:9000/delay/50"
CPU_ROUNDS = 20_000

configure_logging()
stub = requests.Session()
stub.mount("http://", HTTPAdapter(pool_maxsize=256))


def call_stub():
    return stub.get(STUB_URL, timeout=5).json()


def cpu_work():
    digest = b"x"
    for _ in range(CPU_ROUNDS):
        digest = hashlib.sha256(digest).digest()
    return digest.hex()[:16]


def new_book():
    return {"name": f"bench-{uuid.uuid4().hex}", "expected_asset_class": "EQUITY"}


def write_then_read():
    book = repository.create_book(new_book())
    return repository.get_book(str(book["book_id"]))
