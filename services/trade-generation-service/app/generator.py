import logging
import random
import threading
import time
import uuid
from decimal import Decimal

from shared.catalog import INSTRUMENT_CATALOG
from app import action_client, market_data_client
from app.config import CLOSE_PROBABILITY, TRADE_GENERATION_INTERVAL_MS

SYMBOL_BY_CLASS = {terms["asset_class"]: symbol for symbol, terms in INSTRUMENT_CATALOG.items()}

_running = threading.Event()
_lock = threading.Lock()
_books = {}
_open_trades = {}
_stats = {"opened": 0, "closed": 0, "failed": 0}


def set_books(books: dict) -> None:
    with _lock:
        _books.update(books)


def _incr(key: str) -> None:
    with _lock:
        _stats[key] += 1


def _build_open(snapshot: dict) -> dict | None:
    with _lock:
        if not _books:
            return None
        asset_class, book_id = random.choice(list(_books.items()))
    symbol = SYMBOL_BY_CLASS[asset_class]
    terms = INSTRUMENT_CATALOG[symbol]
    price = market_data_client.current_price(snapshot, symbol, terms)
    if price is None:
        return None
    return {
        "action_type": "OPEN_TRADE",
        "client_request_id": f"gen-open-{uuid.uuid4()}",
        "book_id": book_id,
        "asset_class": asset_class,
        "symbol": symbol,
        "side": random.choice(["BUY", "SELL"]),
        "quantity": random.randint(1, 100),
        "trade_price": str(price.quantize(Decimal("0.0001"))),
        "currency": terms.get("currency", "USD"),
        "source": "GENERATED",
    }


def _build_close(snapshot: dict) -> dict | None:
    with _lock:
        if not _open_trades:
            return None
        trade_id, symbol = random.choice(list(_open_trades.items()))
    price = market_data_client.current_price(snapshot, symbol, INSTRUMENT_CATALOG[symbol])
    if price is None:
        return None
    return {
        "action_type": "CLOSE_TRADE",
        "client_request_id": f"gen-close-{uuid.uuid4()}",
        "trade_id": trade_id,
        "symbol": symbol,
        "close_price": str(price.quantize(Decimal("0.0001"))),
        "close_reason": "RANDOM_TRADE_OUT",
    }


def generate_once() -> dict | None:
    snapshot = market_data_client.fetch_snapshot()
    if snapshot is None:
        return None

    intent = None
    if random.random() < CLOSE_PROBABILITY:
        intent = _build_close(snapshot)
    if intent is None:
        intent = _build_open(snapshot)
    if intent is None:
        return None

    ack = action_client.submit(intent)
    if ack is None:
        _incr("failed")
        return None

    if intent["action_type"] == "OPEN_TRADE":
        trade_id = ack.get("trade_id")
        if trade_id:
            with _lock:
                _open_trades[trade_id] = intent["symbol"]
        _incr("opened")
    else:
        with _lock:
            _open_trades.pop(intent["trade_id"], None)
        _incr("closed")
    logging.info("Generated %s (%s)", intent["action_type"], intent["client_request_id"])
    return intent


def run_loop() -> None:
    interval = max(TRADE_GENERATION_INTERVAL_MS, 1) / 1000.0
    while True:
        _running.wait()
        try:
            generate_once()
        except Exception:
            logging.exception("Generation cycle failed")
            _incr("failed")
        time.sleep(interval)


def start() -> None:
    _running.set()


def stop() -> None:
    _running.clear()


def status() -> dict:
    with _lock:
        snapshot = dict(_stats)
        snapshot["open_trades"] = len(_open_trades)
    snapshot["running"] = _running.is_set()
    return snapshot
