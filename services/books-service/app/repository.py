import uuid

from shared.db import session_scope
from shared.models import Book
from shared.functions import utcnow
from shared.audit import write_audit
from shared.logging_config import get_logger
from app.schemas import book_to_dict
from app.config import SERVICE_NAME

log = get_logger(SERVICE_NAME)


def _audit(session, event_type, book, message):
    write_audit(SERVICE_NAME, event_type, message,
                entity_type="BOOK", entity_id=book.book_id, session=session)


def list_books():
    with session_scope() as session:
        return [book_to_dict(b) for b in session.query(Book).order_by(Book.created_at).all()]


def get_book(book_id):
    with session_scope() as session:
        book = session.get(Book, uuid.UUID(book_id))
        return book_to_dict(book) if book else None


def create_book(body):
    now = utcnow()
    with session_scope() as session:
        book = Book(
            book_id=uuid.uuid4(),
            name=body.get("name"),
            description=body.get("description"),
            expected_asset_class=body.get("expected_asset_class"),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(book)
        session.flush()
        _audit(session, "BOOK_CREATED", book, f"Book {book.name} created")
        log.info("book_created", book_id=str(book.book_id), name=book.name,
                 asset_class=book.expected_asset_class)
        return book_to_dict(book)


def update_book(book_id, body):
    with session_scope() as session:
        book = session.get(Book, uuid.UUID(book_id))
        if book is None:
            return None
        for field in ("name", "description", "expected_asset_class", "is_active"):
            if field in body:
                setattr(book, field, body[field])
        book.updated_at = utcnow()
        session.flush()
        event = "BOOK_DELETED" if body.get("is_active") is False else "BOOK_UPDATED"
        _audit(session, event, book, f"Book {book.name} updated")
        log.info("book_deactivated" if event == "BOOK_DELETED" else "book_updated",
                 book_id=str(book.book_id), name=book.name)
        return book_to_dict(book)


def deactivate_book(book_id):
    return update_book(book_id, {"is_active": False})
