import json
import logging
import urllib.request

from shared.catalog import INSTRUMENT_CATALOG
from app.config import BOOKS_URL

ASSET_CLASSES = sorted({terms["asset_class"] for terms in INSTRUMENT_CATALOG.values()})


def _request(url: str, body: dict | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    method = "POST" if body is not None else "GET"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def ensure_books() -> dict:
    existing = {book["expected_asset_class"]: book["book_id"] for book in _request(BOOKS_URL)}
    books = {}
    for asset_class in ASSET_CLASSES:
        if asset_class in existing:
            books[asset_class] = existing[asset_class]
        else:
            created = _request(BOOKS_URL, {"name": f"{asset_class}_DEFAULT",
                                           "expected_asset_class": asset_class})
            books[asset_class] = created["book_id"]
            logging.info("Created default book %s (%s)", created["book_id"], asset_class)
    return books
