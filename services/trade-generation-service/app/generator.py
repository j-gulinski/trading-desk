import random
import threading
import time
import uuid
from decimal import Decimal

from shared.catalog import INSTRUMENT_CATALOG
from shared.logging_config import get_logger
from shared.audit import write_audit
from app import action_client, blotter_client, market_data_client
from app.config import (
    SERVICE_NAME,
    TARGET_OPEN_TRADES,
    TRADE_GENERATION_INTERVAL_MS,
    TARGET_NOTIONAL,
)

log = get_logger(SERVICE_NAME)

SYMBOL_BY_CLASS = {terms["asset_class"]: symbol for symbol, terms in INSTRUMENT_CATALOG.items()}

MIN_INTERVAL_MS = 100
MAX_INTERVAL_MS = 60_000
MIN_TARGET_OPEN_TRADES = 1
MAX_TARGET_OPEN_TRADES = 10_000


def _clamp_interval_ms(value) -> int:
    return max(MIN_INTERVAL_MS, min(int(value), MAX_INTERVAL_MS))


def _clamp_target(value) -> int:
    return max(MIN_TARGET_OPEN_TRADES, min(int(value), MAX_TARGET_OPEN_TRADES))


def _close_probability_of(open_count: int, target: int) -> float:
    return min(0.9, 0.5 * open_count / max(target, 1))


_running = threading.Event()
_lock = threading.Lock()
_books = {}
_open_trades = {}
_stats = {"opened": 0, "closed": 0, "failed": 0}
_config = {
    "interval_ms": _clamp_interval_ms(TRADE_GENERATION_INTERVAL_MS),
    "target_open_trades": _clamp_target(TARGET_OPEN_TRADES),
}
_config_wait = threading.Event()
_last_open_sync_ms = 0
_ACTIVE_OPEN_TRADES_SYNC_MS = 10_000


def set_books(books: dict) -> None:
    with _lock:
        _books.update(books)


def sync_open_trades() -> int:
    global _open_trades, _last_open_sync_ms
    active_trades = blotter_client.active_trades()
    with _lock:
        _open_trades = {
            trade_id: symbol
            for trade_id, symbol in active_trades.items()
            if symbol in INSTRUMENT_CATALOG
        }
        tracked = len(_open_trades)
    _last_open_sync_ms = int(time.time() * 1000)
    return tracked


def _sync_open_trades_if_due() -> None:
    if int(time.time() * 1000) - _last_open_sync_ms < _ACTIVE_OPEN_TRADES_SYNC_MS:
        return
    try:
        sync_open_trades()
    except Exception:
        log.exception("open_trades_sync_failed")


def get_config() -> dict:
    with _lock:
        return dict(_config)


def set_config(*, interval_ms=None, target_open_trades=None) -> dict:
    if interval_ms is not None:
        interval_ms = _clamp_interval_ms(interval_ms)
    if target_open_trades is not None:
        target_open_trades = _clamp_target(target_open_trades)
    with _lock:
        if interval_ms is not None:
            _config["interval_ms"] = interval_ms
        if target_open_trades is not None:
            _config["target_open_trades"] = target_open_trades
        applied = dict(_config)
    _config_wait.set()
    write_audit(SERVICE_NAME, "CONFIG_CHANGED",
                f"Generation config set to {applied}", payload=applied)
    return applied


def _interval_seconds() -> float:
    with _lock:
        return _config["interval_ms"] / 1000.0


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


def _close_probability() -> float:
    with _lock:
        return _close_probability_of(len(_open_trades), _config["target_open_trades"])


def generate_once() -> dict | None:
    snapshot = market_data_client.fetch_snapshot()
    if snapshot is None:
        return None

    intent = None
    if random.random() < _close_probability():
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
    while True:
        _running.wait()
        while _running.is_set():
            try:
                _sync_open_trades_if_due()
                generate_once()
            except Exception:
                log.exception("generation_failed")
                _incr("failed")
            _config_wait.wait(_interval_seconds())
            _config_wait.clear()


def start() -> None:
    _running.set()
    _config_wait.set()
    write_audit(SERVICE_NAME, "WORKER_STARTED", "Generation loop started")


def stop() -> None:
    _running.clear()
    _config_wait.set()
    write_audit(SERVICE_NAME, "WORKER_STOPPED", "Generation loop stopped")


def status() -> dict:
    with _lock:
        snapshot = dict(_stats)
        open_count = len(_open_trades)
        config = dict(_config)
    snapshot["open_trades"] = open_count
    snapshot["config"] = config
    snapshot["close_probability"] = _close_probability_of(open_count, config["target_open_trades"])
    snapshot["running"] = _running.is_set()
    return snapshot
