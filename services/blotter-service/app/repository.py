import uuid
from decimal import Decimal

from sqlalchemy import func

from shared.db import session_scope
from shared.models import Trade, Valuation, AuditLog, Book
from app.cache import Trade as CachedTrade


def _to_cached_trade(row: Trade) -> CachedTrade:
    return CachedTrade(
        trade_id=str(row.trade_id),
        book_id=str(row.book_id),
        asset_class=row.asset_class,
        symbol=row.symbol,
        side=row.side,
        status=row.status,
        quantity=row.quantity,
        trade_price=row.trade_price,
        currency=row.trade_currency,
        opened_at=row.opened_at,
        closed_at=row.closed_at,
        close_price=row.close_price,
        close_reason=row.close_reason,
        market_data_provider=row.market_data_provider,
        entry_price_timestamp=row.entry_price_timestamp,
        entry_snapshot_id=str(row.entry_snapshot_id) if row.entry_snapshot_id else None,
        close_price_timestamp=row.close_price_timestamp,
        close_snapshot_id=str(row.close_snapshot_id) if row.close_snapshot_id else None,
        client_seen_price=row.client_seen_price,
    )


def load_active_trades() -> list[CachedTrade]:
    with session_scope() as session:
        rows = session.query(Trade).filter(Trade.status == "ACTIVE").all()
        return [_to_cached_trade(r) for r in rows]


def get_trade(trade_id: str) -> CachedTrade | None:
    with session_scope() as session:
        row = session.get(Trade, uuid.UUID(trade_id))
        return _to_cached_trade(row) if row else None


def list_trades(*, book_id=None, asset_class=None, status=None, symbol=None,
                exclude_active=False, limit: int = 100, offset: int = 0) -> list[CachedTrade]:
    with session_scope() as session:
        q = session.query(Trade)
        if book_id is not None:
            q = q.filter(Trade.book_id == uuid.UUID(book_id))
        if asset_class is not None:
            q = q.filter(Trade.asset_class == asset_class)
        if status is not None:
            q = q.filter(Trade.status == status)
        elif exclude_active:
            q = q.filter(Trade.status != "ACTIVE")
        if symbol is not None:
            q = q.filter(Trade.symbol == symbol)
        rows = (
            q.order_by(Trade.opened_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return [_to_cached_trade(r) for r in rows]


def closed_trade_counts_by_book() -> dict[str, int]:
    with session_scope() as session:
        rows = (
            session.query(Trade.book_id, func.count(Trade.trade_id))
            .filter(Trade.status != "ACTIVE")
            .group_by(Trade.book_id)
            .all()
        )
        return {str(book_id): count for book_id, count in rows}


def realized_pnl_by_book() -> dict[str, object]:
    totals: dict[str, object] = {}
    with session_scope() as session:
        rows = session.query(Trade).filter(Trade.status == "CLOSED").all()
        for t in rows:
            if t.close_price is None:
                continue
            multiplier = int((t.trade_metadata or {}).get("multiplier", 1))
            if t.side == "SELL":
                realized = (t.trade_price - t.close_price) * t.quantity * multiplier
            else:
                realized = (t.close_price - t.trade_price) * t.quantity * multiplier
            book_id = str(t.book_id)
            totals[book_id] = (totals.get(book_id) or Decimal("0")) + realized
    return totals


def valuation_history(trade_id: str, limit: int = 100) -> list[dict]:
    with session_scope() as session:
        rows = (
            session.query(Valuation)
            .filter(Valuation.trade_id == uuid.UUID(trade_id))
            .order_by(Valuation.valuation_time.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "valuation_time": v.valuation_time,
                "fair_value": v.fair_value,
                "unrealized_pnl": v.unrealized_pnl,
                "realized_pnl": v.realized_pnl,
                "total_pnl": v.total_pnl,
                "currency": v.currency,
            }
            for v in rows
        ]


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
