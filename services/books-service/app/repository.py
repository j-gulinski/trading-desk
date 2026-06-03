import uuid

from shared.db import session_scope
from shared.models import Book
from shared.functions import utcnow
from app.schemas import book_to_dict


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
        return book_to_dict(book)


def deactivate_book(book_id):
    return update_book(book_id, {"is_active": False})
