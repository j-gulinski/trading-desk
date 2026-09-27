import uuid

from sqlalchemy.exc import IntegrityError

from desk_runtime.db import session_scope
from desk_domain.models import Book, Trade
from desk_runtime.functions import utcnow
from desk_domain.audit import write_audit
from desk_runtime.logging_config import get_logger
from books_service.schemas import book_to_dict
from books_service.config import SERVICE_NAME

log = get_logger(SERVICE_NAME)


class BookConflict(Exception):
    def __init__(self, message, **fields):
        super().__init__(message)
        self.fields = fields


def _audit(session, event_type, book, message):
    write_audit(SERVICE_NAME, event_type, message,
                entity_type="BOOK", entity_id=book.book_id, session=session)


def _locked_book(session, book_id):
    return (
        session.query(Book).filter(Book.book_id == uuid.UUID(book_id))
        .with_for_update().one_or_none()
    )


def _open_trades(session, book):
    return (
        session.query(Trade)
        .filter(Trade.book_id == book.book_id, Trade.status == "ACTIVE")
        .count()
    )


def list_books():
    with session_scope() as session:
        return [book_to_dict(b) for b in session.query(Book).order_by(Book.created_at).all()]


def get_book(book_id):
    with session_scope() as session:
        book = session.get(Book, uuid.UUID(book_id))
        return book_to_dict(book) if book else None


def create_book(fields):
    now = utcnow()
    try:
        with session_scope() as session:
            book = Book(book_id=uuid.uuid4(), is_active=True, created_at=now, updated_at=now,
                        **fields)
            session.add(book)
            session.flush()
            _audit(session, "BOOK_CREATED", book, f"Book {book.name} created")
            log.info("book_created", book_id=str(book.book_id), name=book.name,
                     asset_class=book.expected_asset_class)
            return book_to_dict(book)
    except IntegrityError as exc:
        raise BookConflict("a book with this name already exists", name=fields.get("name")) from exc


def update_book(book_id, fields):
    try:
        with session_scope() as session:
            book = _locked_book(session, book_id)
            if book is None:
                return None
            changes_class = fields.get("expected_asset_class", book.expected_asset_class) \
                != book.expected_asset_class
            if changes_class and (open_trades := _open_trades(session, book)):
                raise BookConflict("book has open trades", book_id=book_id,
                                   active_trades=open_trades)
            for field, value in fields.items():
                setattr(book, field, value)
            book.updated_at = utcnow()
            session.flush()
            _audit(session, "BOOK_UPDATED", book, f"Book {book.name} updated")
            log.info("book_updated", book_id=book_id, name=book.name)
            return book_to_dict(book)
    except IntegrityError as exc:
        raise BookConflict("a book with this name already exists", name=fields.get("name")) from exc


def deactivate_book(book_id):
    with session_scope() as session:
        book = _locked_book(session, book_id)
        if book is None:
            return None
        if open_trades := _open_trades(session, book):
            raise BookConflict("book has open trades", book_id=book_id, active_trades=open_trades)
        book.is_active = False
        book.updated_at = utcnow()
        _audit(session, "BOOK_DELETED", book, f"Book {book.name} updated")
        log.info("book_deactivated", book_id=book_id, name=book.name)
        return book_to_dict(book)
