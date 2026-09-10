import uuid

from sqlalchemy import update

from desk_domain.models import Trade, Book
from desk_domain.contract_data import split_terms
from desk_domain.instrument_store import ensure_instrument, lock_instrument, require_watched_source
from desk_runtime.functions import utcnow
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


def insert_trade(session, intent, instrument, market_data_provider, executed_price, quote):
    now = utcnow()
    symbol = intent.get("symbol")
    trade_id = uuid.UUID(intent["trade_id"])
    asset_class = instrument.asset_class
    currency = quote.currency or instrument.terms["currency"]
    data = split_terms(instrument)
    if instrument.symbol_prefix is not None:
        underlying = None
        if instrument.underlying_field:
            underlying = lock_instrument(session, instrument.quote_symbol)
            require_watched_source(session, underlying, market_data_provider)
            if underlying.asset_class not in instrument.underlying_asset_classes \
                    or underlying.currency != currency:
                raise ValueError(
                    f"{asset_class} underlying must be "
                    f"{' or '.join(instrument.underlying_asset_classes)} in the contract currency"
                )
        row = ensure_instrument(
            session, symbol, asset_class, currency, terms=data.terms,
            underlying_id=underlying.instrument_id if underlying else None,
        )
    else:
        row = lock_instrument(session, symbol)
        require_watched_source(session, row, market_data_provider)
        if row.asset_class != asset_class or row.currency != currency:
            raise ValueError("execution does not match instrument identity")
    trade = Trade(
        trade_id=trade_id,
        book_id=uuid.UUID(intent["book_id"]),
        instrument_id=row.instrument_id,
        side=intent.get("side"),
        quantity=intent.get("quantity"),
        trade_price=executed_price,
        trade_currency=currency,
        market_data_provider=market_data_provider,
        entry_price_timestamp=quote.provider_timestamp,
        entry_snapshot_id=quote.snapshot_id,
        client_seen_price=intent.get("client_seen_price"),
        created_by_service=SERVICE_NAME,
        status="ACTIVE",
        opened_at=now,
        source=intent.get("source") or "MANUAL",
        client_request_id=intent.get("client_request_id"),
        trade_metadata=data.metadata(),
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
