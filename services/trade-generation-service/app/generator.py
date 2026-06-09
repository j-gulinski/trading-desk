import random
import threading
import time
import uuid
from decimal import Decimal

from shared.catalog import INSTRUMENT_CATALOG
from shared.logging_config import get_logger
from shared.audit import write_audit
from app import action_client, market_data_client
from app.config import SERVICE_NAME, CLOSE_PROBABILITY, TRADE_GENERATION_INTERVAL_MS, TARGET_NOTIONAL

log = get_logger(SERVICE_NAME)

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
        "quantity": _size_quantity(price, terms.get("multiplier", 1)),
        "trade_price": str(price.quantize(Decimal("0.0001"))),
        "currency": terms.get("currency", "USD"),
        "source": "GENERATED",
    }


def _size_quantity(price: Decimal, multiplier: int) -> int:
    notional = TARGET_NOTIONAL * random.uniform(0.5, 1.5)
    return max(1, round(notional / (float(price) * multiplier)))


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
    log.info("generated", action=intent["action_type"], crid=intent["client_request_id"])
    return intent


def run_loop() -> None:
    interval = max(TRADE_GENERATION_INTERVAL_MS, 1) / 1000.0
    while True:
        _running.wait()
        try:
            generate_once()
        except Exception:
            log.exception("generation_failed")
            _incr("failed")
        time.sleep(interval)


def start() -> None:
    _running.set()
    write_audit(SERVICE_NAME, "WORKER_STARTED", "Generation loop started")


def stop() -> None:
    _running.clear()
    write_audit(SERVICE_NAME, "WORKER_STOPPED", "Generation loop stopped")


def status() -> dict:
    with _lock:
        snapshot = dict(_stats)
        snapshot["open_trades"] = len(_open_trades)
    snapshot["running"] = _running.is_set()
    return snapshot
