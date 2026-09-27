import uuid

from sqlalchemy import and_, func

from desk_domain.contract_data import trade_terms
from desk_domain.instruments import instrument_type_for, type_view_for
from desk_domain.models import AuditLog, Book, Instrument, Trade, Valuation
from desk_runtime.db import session_scope


def _trade_record(trade: Trade) -> dict:
    asset_class = trade.instrument.asset_class
    return {
        "trade_id": str(trade.trade_id),
        "book_id": str(trade.book_id),
        "asset_class": asset_class,
        **type_view_for(asset_class),
        "symbol": trade.instrument.symbol,
        "side": trade.side,
        "quantity": trade.quantity,
        "trade_price": trade.trade_price,
        "currency": trade.trade_currency,
        "status": trade.status,
        "opened_at": trade.opened_at,
        "closed_at": trade.closed_at,
        "close_price": trade.close_price,
        "close_reason": trade.close_reason,
        "market_data_provider": trade.market_data_provider,
        "entry_price_timestamp": trade.entry_price_timestamp,
        "entry_snapshot_id": trade.entry_snapshot_id,
        "close_price_timestamp": trade.close_price_timestamp,
        "close_snapshot_id": trade.close_snapshot_id,
        "client_seen_price": trade.client_seen_price,
        "source": trade.source,
        "created_by_service": trade.created_by_service,
        "terms": trade_terms(trade),
        "model_priced": instrument_type_for(asset_class).ticket_kind != "spot",
    }


def _valuation_record(valuation: Valuation) -> dict:
    return {
        "valuation_time": valuation.valuation_time,
        "fair_value": valuation.fair_value,
        "unrealized_pnl": valuation.unrealized_pnl,
        "realized_pnl": valuation.realized_pnl,
        "total_pnl": valuation.total_pnl,
        "currency": valuation.currency,
        "market_data_provider": valuation.market_data_provider,
        "market_data_timestamp": valuation.market_data_timestamp,
        "valuation_payload": valuation.valuation_payload or {},
    }


def list_trades(*, book_id=None, asset_class=None, status=None, symbol=None,
                limit=100, offset=0) -> list[dict]:
    with session_scope() as session:
        query = session.query(Trade).join(Trade.instrument)
        if book_id is not None:
            query = query.filter(Trade.book_id == uuid.UUID(book_id))
        if asset_class is not None:
            query = query.filter(Instrument.asset_class == asset_class)
        if status is not None:
            query = query.filter(Trade.status == status)
        if symbol is not None:
            query = query.filter(Instrument.symbol == symbol)
        rows = query.order_by(Trade.opened_at.desc()).limit(limit).offset(offset).all()
        return [_trade_record(row) for row in rows]


def get_trade(trade_id: str) -> dict | None:
    with session_scope() as session:
        row = session.get(Trade, uuid.UUID(trade_id))
        return _trade_record(row) if row else None


def active_trades() -> list[dict]:
    with session_scope() as session:
        rows = (
            session.query(Trade)
            .filter(Trade.status == "ACTIVE")
            .order_by(Trade.opened_at.desc())
            .all()
        )
        return [_trade_record(row) for row in rows]


def latest_valuations(trade_ids: list[str]) -> dict[str, dict]:
    if not trade_ids:
        return {}
    with session_scope() as session:
        rows = (
            session.query(Valuation)
            .filter(Valuation.trade_id.in_([uuid.UUID(trade_id) for trade_id in trade_ids]))
            .order_by(Valuation.trade_id, Valuation.valuation_time.desc())
            .distinct(Valuation.trade_id)
            .all()
        )
        return {str(row.trade_id): _valuation_record(row) for row in rows}


def closed_trade_totals() -> list[dict]:
    """Closed trade count and final realized P&L per book and currency."""
    final = and_(
        Valuation.trade_id == Trade.trade_id,
        Valuation.valuation_payload["final"].as_boolean().is_(True),
    )
    with session_scope() as session:
        rows = (
            session.query(
                Trade.book_id,
                Trade.trade_currency,
                func.count(Trade.trade_id),
                func.coalesce(func.sum(Valuation.realized_pnl), 0),
            )
            .outerjoin(Valuation, final)
            .filter(Trade.status == "CLOSED")
            .group_by(Trade.book_id, Trade.trade_currency)
            .all()
        )
        return [
            {
                "book_id": str(book_id),
                "currency": currency,
                "trades": trades,
                "realized_pnl": realized_pnl,
            }
            for book_id, currency, trades, realized_pnl in rows
        ]


def valuation_history(trade_id: str, limit: int = 100) -> list[dict]:
    with session_scope() as session:
        rows = (
            session.query(Valuation)
            .filter(Valuation.trade_id == uuid.UUID(trade_id))
            .order_by(Valuation.valuation_time.desc())
            .limit(limit)
            .all()
        )
        return [_valuation_record(row) for row in rows]


def audit_logs(trade_id: str, limit: int = 100) -> list[dict]:
    with session_scope() as session:
        rows = (
            session.query(AuditLog)
            .filter(AuditLog.entity_id == trade_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "created_at": a.created_at,
                "service_name": a.service_name,
                "event_type": a.event_type,
                "severity": a.severity,
                "message": a.message,
            }
            for a in rows
        ]


def list_books() -> list[dict]:
    with session_scope() as session:
        rows = session.query(Book).order_by(Book.created_at).all()
        return [
            {
                "book_id": str(b.book_id),
                "name": b.name,
                "expected_asset_class": b.expected_asset_class,
                "is_active": b.is_active,
            }
            for b in rows
        ]
