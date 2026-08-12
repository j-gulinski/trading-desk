import math
import re
import time
import uuid

import structlog
from sqlalchemy.exc import IntegrityError

from shared.db import session_scope
from shared.catalog import INSTRUMENT_CATALOG
from shared.term_schemas import validate_terms
from shared.audit import write_audit
from shared.logging_config import get_logger
from app import action_queue, repository
from app.config import SERVICE_NAME

log = get_logger(SERVICE_NAME)

_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_.\-]{1,31}$")


def _audit(session, event_type, message, intent, severity="INFO"):
    write_audit(SERVICE_NAME, event_type, message, entity_type="TRADE",
                entity_id=intent.get("trade_id"), correlation_id=intent.get("client_request_id"),
                severity=severity, session=session)


def _resolve_terms(intent):
    asset_class = intent.get("asset_class")
    custom = intent.get("terms")
    if custom is not None:
        symbol = intent.get("symbol")
        if not isinstance(symbol, str) or not _SYMBOL_PATTERN.match(symbol):
            return None, "invalid custom instrument symbol"
        return validate_terms(asset_class, custom)
    terms = INSTRUMENT_CATALOG.get(intent.get("symbol"))
    if terms is None or terms["asset_class"] != asset_class:
        return None, "unknown catalog instrument for asset class"
    return terms, None


def _price_error(intent):
    try:
        price = float(intent.get("trade_price"))
    except (TypeError, ValueError):
        return "invalid trade price"
    if not math.isfinite(price):
        return "invalid trade price"
    if price <= 0.0 and intent.get("asset_class") != "IRS":
        return "non-positive trade price"
    return None


def _open(intent):
    book_id = _parse_uuid(intent.get("book_id"))
    terms, term_error = _resolve_terms(intent)
    price_error = _price_error(intent)
    try:
        with session_scope() as session:
            book = repository.get_active_book(session, book_id) if book_id else None
            if (
                book is None
                or book.expected_asset_class != intent.get("asset_class")
                or terms is None
                or price_error is not None
            ):
                message = term_error or price_error or "bad book or asset class"
                log.warning("open_rejected", reason=message, book_id=intent.get("book_id"),
                            symbol=intent.get("symbol"), trade_id=intent.get("trade_id"))
                _audit(session, "ACTION_REJECTED", f"Open rejected: {message}", intent, "WARNING")
                return action_queue.incr("rejected")
            repository.insert_trade(session, intent, terms)
            _audit(session, "TRADE_CREATED", "Trade created", intent)
        log.info("trade_created", trade_id=intent.get("trade_id"), symbol=intent.get("symbol"),
                 book_id=intent.get("book_id"), side=intent.get("side"),
                 quantity=intent.get("quantity"))
        action_queue.incr("created")
    except IntegrityError:
        log.warning("duplicate_intent", trade_id=intent.get("trade_id"))
        action_queue.incr("duplicates")


def _close(intent):
    with session_scope() as session:
        closed = repository.close_trade(session, uuid.UUID(intent["trade_id"]),
                                        intent.get("close_price"), intent.get("close_reason"))
        if closed:
            _audit(session, "TRADE_CLOSED", "Trade closed", intent)
        else:
            _audit(session, "ACTION_REJECTED", "Close rejected: not ACTIVE", intent, "WARNING")
    if closed:
        log.info("trade_closed", trade_id=intent.get("trade_id"),
                 close_reason=intent.get("close_reason"))
    else:
        log.warning("close_rejected", trade_id=intent.get("trade_id"), reason="not ACTIVE")
    action_queue.incr("closed" if closed else "rejected")


def _close_all(intent):
    reason = intent.get("close_reason") or "CLOSE_ALL"
    with session_scope() as session:
        trade_ids = repository.close_all_trades(session, reason)
        for trade_id in trade_ids:
            write_audit(SERVICE_NAME, "TRADE_CLOSED", "Trade closed",
                        entity_type="TRADE", entity_id=trade_id,
                        payload={"close_reason": reason}, session=session)
    log.info("close_all_processed", closed=len(trade_ids), close_reason=reason)
    action_queue.incr("closed", len(trade_ids))


def _reassign(intent):
    source_id = _parse_uuid(intent.get("book_id"))
    target_id = _parse_uuid(intent.get("target_book_id"))

    def reject(session, message):
        log.warning("reassign_rejected", reason=message,
                    book_id=str(source_id) if source_id else None,
                    target_book_id=str(target_id) if target_id else None)
        write_audit(SERVICE_NAME, "ACTION_REJECTED", message, entity_type="BOOK",
                    entity_id=str(source_id) if source_id else None,
                    correlation_id=intent.get("client_request_id"),
                    severity="WARNING", session=session)
        return action_queue.incr("rejected")

    with session_scope() as session:
        source = repository.get_book(session, source_id) if source_id else None
        target = repository.get_active_book(session, target_id) if target_id else None
        if source is None or target is None or source_id == target_id:
            return reject(session, "Reassign rejected: unknown or same book")
        if source.expected_asset_class != target.expected_asset_class:
            return reject(session, "Reassign rejected: asset class mismatch")
        trade_ids = repository.reassign_active_trades(session, source_id, target_id)
        for trade_id in trade_ids:
            write_audit(SERVICE_NAME, "TRADE_REASSIGNED",
                        f"Trade moved from {source.name} to {target.name}",
                        entity_type="TRADE", entity_id=trade_id,
                        payload={"from_book_id": str(source_id), "to_book_id": str(target_id)},
                        correlation_id=intent.get("client_request_id"), session=session)
    log.info("trades_reassigned", count=len(trade_ids),
             from_book_id=str(source_id), to_book_id=str(target_id))
    action_queue.incr("reassigned", len(trade_ids))


def _process(intent):
    action = intent.get("action_type")
    if action == "CLOSE_TRADE":
        _close(intent)
    elif action == "CLOSE_ALL":
        _close_all(intent)
    elif action == "REASSIGN_TRADES":
        _reassign(intent)
    else:
        _open(intent)


def _parse_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def worker_loop():
    log.info("worker_started")
    write_audit(SERVICE_NAME, "WORKER_STARTED", "Trade-action worker started")
    failing = False
    while True:
        intent = action_queue.intents.get()
        started = time.perf_counter()
        correlation_id = intent.get("client_request_id")
        if correlation_id:
            structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        log.info("intent_dequeued", action=intent.get("action_type"),
                 trade_id=intent.get("trade_id"))
        try:
            _process(intent)
            if failing:
                failing = False
                log.info("worker_recovered")
                write_audit(SERVICE_NAME, "WORKER_RECOVERED",
                            "Trade-action worker processing again",
                            correlation_id=correlation_id)
        except Exception as exc:
            log.exception("process_failed", action=intent.get("action_type"),
                          trade_id=intent.get("trade_id"))
            if not failing:
                failing = True
                write_audit(SERVICE_NAME, "WORKER_FAILED",
                            f"Trade-action processing failed: {type(exc).__name__}",
                            correlation_id=correlation_id, severity="ERROR")
        finally:
            structlog.contextvars.unbind_contextvars("correlation_id")
            action_queue.record_processed(int((time.perf_counter() - started) * 1000))
