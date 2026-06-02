import uuid
import logging

from sqlalchemy.exc import IntegrityError

from shared.db import session_scope
from shared.catalog import INSTRUMENT_CATALOG
from app import action_queue, repository


def _process(intent):
    if intent.get("action_type") == "CLOSE_TRADE":
        with session_scope() as session:
            updated = repository.close_trade(
                session, uuid.UUID(intent["trade_id"]),
                intent.get("close_price"), intent.get("close_reason"),
            )
        action_queue.incr("closed" if updated == 1 else "rejected")
        return

    book_id = _parse_uuid(intent.get("book_id"))
    terms = INSTRUMENT_CATALOG.get(intent.get("symbol"))
    try:
        with session_scope() as session:
            book = repository.get_active_book(session, book_id) if book_id else None
            if book is None:
                action_queue.incr("rejected")
                logging.warning("Rejected open: book %s not found or inactive", intent.get("book_id"))
                return
            if book.expected_asset_class != intent.get("asset_class"):
                action_queue.incr("rejected")
                logging.warning(
                    "Rejected open: asset_class %s != book.expected_asset_class %s",
                    intent.get("asset_class"), book.expected_asset_class,
                )
                return
            repository.insert_trade(session, intent, terms)
        action_queue.incr("created")
    except IntegrityError:
        action_queue.incr("duplicates")


def _parse_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def worker_loop():
    logging.info("Trade-action worker started")
    while True:
        intent = action_queue.intents.get()
        try:
            _process(intent)
        except Exception:
            logging.exception("Failed to process intent")
        finally:
            action_queue.incr("processed")
            action_queue.intents.task_done()
