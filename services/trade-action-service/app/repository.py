import uuid

from sqlalchemy import update

from shared.models import Trade, Book
from shared.functions import utcnow


def get_book(session, book_id):
    return session.get(Book, book_id)


def get_active_book(session, book_id):
    book = session.get(Book, book_id)
    if book is None or not book.is_active:
        return None
    return book


def insert_trade(session, intent, terms):
    now = utcnow()
    symbol = intent.get("symbol")
    trade = Trade(
        trade_id=uuid.UUID(intent["trade_id"]),
        book_id=uuid.UUID(intent["book_id"]),
        asset_class=intent.get("asset_class"),
        instrument_id=symbol,
        symbol=symbol,
        side=intent.get("side"),
        quantity=intent.get("quantity"),
        trade_price=intent.get("trade_price"),
        trade_currency=intent.get("currency") or "USD",
        trade_date=now,
        status="ACTIVE",
        opened_at=now,
        source=intent.get("source") or "MANUAL",
        client_request_id=intent.get("client_request_id"),
        trade_metadata=terms,
        created_at=now,
        updated_at=now,
    )
    session.add(trade)
    return trade


def close_trade(session, trade_id, close_price, close_reason) -> int:
    now = utcnow()
    result = session.execute(
        update(Trade)
        .where(Trade.trade_id == trade_id, Trade.status == "ACTIVE")
        .values(
            status="CLOSED",
            close_price=close_price,
            close_reason=close_reason,
            closed_at=now,
            updated_at=now,
            valuation_finalized=False,
        )
    )
    return result.rowcount


def reassign_active_trades(session, source_book_id, target_book_id) -> list:
    now = utcnow()
    result = session.execute(
        update(Trade)
        .where(Trade.book_id == source_book_id, Trade.status == "ACTIVE")
        .values(book_id=target_book_id, updated_at=now)
        .returning(Trade.trade_id)
    )
    return [row[0] for row in result]


def close_all_trades(session, close_reason) -> list:
    now = utcnow()
    result = session.execute(
        update(Trade)
        .where(Trade.status == "ACTIVE")
        .values(
            status="CLOSED",
            close_reason=close_reason,
            closed_at=now,
            updated_at=now,
            valuation_finalized=False,
        )
        .returning(Trade.trade_id)
    )
    return [row[0] for row in result]
