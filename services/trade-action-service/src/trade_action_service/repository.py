import uuid

from sqlalchemy import update

from desk_domain.models import Trade, Book
from desk_runtime.functions import utcnow
from desk_domain.symbols import CURVE_PRICED_ASSET_CLASSES
from trade_action_service.config import SERVICE_NAME


def get_book(session, book_id):
    return session.get(Book, book_id)


def get_active_book(session, book_id):
    book = session.get(Book, book_id)
    if book is None or not book.is_active:
        return None
    return book


def trade_by_client_request_id(session, client_request_id):
    return session.query(Trade).filter_by(client_request_id=client_request_id).one_or_none()


def insert_trade(session, intent, terms, market_data_provider, executed_price, quote):
    now = utcnow()
    symbol = intent.get("symbol")
    trade_id = uuid.UUID(intent["trade_id"])
    trade = Trade(
        trade_id=trade_id,
        book_id=uuid.UUID(intent["book_id"]),
        asset_class=intent.get("asset_class"),
        instrument_id=(
            str(trade_id)
            if intent.get("asset_class") in CURVE_PRICED_ASSET_CLASSES
            else symbol
        ),
        symbol=symbol,
        side=intent.get("side"),
        quantity=intent.get("quantity"),
        trade_price=executed_price,
        trade_currency=quote.currency or intent.get("currency") or "USD",
        market_data_provider=market_data_provider,
        entry_price_timestamp=quote.provider_timestamp,
        entry_snapshot_id=quote.snapshot_id,
        client_seen_price=intent.get("client_seen_price"),
        created_by_service=SERVICE_NAME,
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


def active_trade(session, trade_id):
    return (
        session.query(Trade)
        .filter(Trade.trade_id == trade_id, Trade.status == "ACTIVE")
        .one_or_none()
    )


def active_trades(session):
    return session.query(Trade).filter(Trade.status == "ACTIVE").all()


def close_trade(
    session, trade_id, close_price, close_reason, quote, trade_metadata=None
) -> int:
    now = utcnow()
    values = dict(
        status="CLOSED",
        close_price=close_price,
        close_price_timestamp=quote.provider_timestamp,
        close_snapshot_id=quote.snapshot_id,
        close_reason=close_reason,
        closed_at=now,
        updated_at=now,
        valuation_finalized=False,
    )
    if trade_metadata is not None:
        values["trade_metadata"] = trade_metadata
    result = session.execute(
        update(Trade)
        .where(Trade.trade_id == trade_id, Trade.status == "ACTIVE")
        .values(**values)
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
