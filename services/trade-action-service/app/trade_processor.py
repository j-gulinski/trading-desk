import uuid

from sqlalchemy.exc import IntegrityError

from shared.db import session_scope
from shared.catalog import INSTRUMENT_CATALOG
from shared.audit import write_audit
from shared.logging_config import get_logger
from app import action_queue, repository
from app.config import SERVICE_NAME

log = get_logger(SERVICE_NAME)


def _audit(session, event_type, message, intent, severity="INFO"):
    write_audit(SERVICE_NAME, event_type, message, entity_type="TRADE",
                entity_id=intent.get("trade_id"), correlation_id=intent.get("client_request_id"),
                severity=severity, session=session)


def _open(intent):
    book_id = _parse_uuid(intent.get("book_id"))
    terms = INSTRUMENT_CATALOG.get(intent.get("symbol"))
    try:
        with session_scope() as session:
            book = repository.get_active_book(session, book_id) if book_id else None
            if book is None or book.expected_asset_class != intent.get("asset_class"):
                _audit(session, "ACTION_REJECTED", "Open rejected: bad book or asset class", intent, "WARNING")
                return action_queue.incr("rejected")
            repository.insert_trade(session, intent, terms)
            _audit(session, "TRADE_CREATED", "Trade created", intent)
        action_queue.incr("created")
    except IntegrityError:
        action_queue.incr("duplicates")


def _close(intent):
    with session_scope() as session:
        closed = repository.close_trade(session, uuid.UUID(intent["trade_id"]),
                                        intent.get("close_price"), intent.get("close_reason"))
        if closed:
            _audit(session, "TRADE_CLOSED", "Trade closed", intent)
        else:
            _audit(session, "ACTION_REJECTED", "Close rejected: not ACTIVE", intent, "WARNING")
    action_queue.incr("closed" if closed else "rejected")


def _close_all(intent):
    reason = intent.get("close_reason") or "CLOSE_ALL"
    with session_scope() as session:
        trade_ids = repository.close_all_trades(session, reason)
        for trade_id in trade_ids:
            write_audit(SERVICE_NAME, "TRADE_CLOSED", "Trade closed",
                        entity_type="TRADE", entity_id=trade_id,
                        payload={"close_reason": reason}, session=session)
    action_queue.incr("closed", len(trade_ids))


def _process(intent):
    action = intent.get("action_type")
    if action == "CLOSE_TRADE":
        _close(intent)
    elif action == "CLOSE_ALL":
        _close_all(intent)
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
    while True:
        intent = action_queue.intents.get()
        try:
            _process(intent)
        except Exception:
            log.exception("process_failed")
        finally:
            action_queue.incr("processed")
