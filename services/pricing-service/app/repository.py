"""Database reads and writes used by the pricing process."""

import datetime
import uuid
from decimal import Decimal

from app.config import SERVICE_NAME, VALUATION_WRITE_INTERVAL_SECONDS
from app.pnl import signed_quantity
from shared.db import session_scope
from shared.functions import get_iso_timestamp, utcnow
from shared.logging_config import get_logger
from shared.audit import write_audit
from sqlalchemy import and_, func

from shared.models import Book, Trade, Valuation

log = get_logger(SERVICE_NAME)

VALUATION_PERSISTED = "PERSISTED"
VALUATION_THROTTLED = "THROTTLED"
VALUATION_PERSIST_BLOCKED = "BLOCKED"

CURVE_PROVENANCE_FIELDS = (
    "discount_curve",
    "discount_curve_provider",
    "discount_curve_as_of",
    "projection_curve",
    "projection_curve_provider",
    "projection_curve_as_of",
    "close_discount_curve_provider",
    "close_discount_curve_as_of",
    "close_projection_curve_provider",
    "close_projection_curve_as_of",
)


def _trades_with_book(session):
    return session.query(Trade, Book.name).join(Book, Book.book_id == Trade.book_id)


def load_active_trades():
    """Read the durable active set into the pricing service's domain shape."""
    active = {}
    with session_scope() as session:
        rows = _trades_with_book(session).filter(Trade.status == "ACTIVE").all()
        for trade, book_name in rows:
            active[str(trade.trade_id)] = {
                "trade_id": str(trade.trade_id),
                "book_id": str(trade.book_id),
                "book_name": book_name,
                "asset_class": trade.asset_class,
                "symbol": trade.symbol,
                "side": trade.side,
                "quantity": trade.quantity,
                "trade_price": trade.trade_price,
                "currency": trade.trade_currency,
                "market_data_provider": trade.market_data_provider,
                "metadata": trade.trade_metadata or {},
            }
    return active


def _parse_timestamp(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def save_valuation(valuation):
    try:
        with session_scope() as session:
            now = utcnow()
            active_trade = (
                session.query(Trade.trade_id, Trade.book_id)
                .filter(
                    Trade.trade_id == uuid.UUID(valuation["trade_id"]),
                    Trade.status == "ACTIVE",
                )
                .with_for_update()
                .one_or_none()
            )
            if active_trade is None:
                log.debug(
                    "valuation_persist_skipped_closed_trade",
                    trade_id=valuation.get("trade_id"),
                )
                return VALUATION_PERSIST_BLOCKED
            if str(active_trade.book_id) != str(valuation.get("book_id")):
                log.debug(
                    "valuation_persist_skipped_reassigned_trade",
                    trade_id=valuation.get("trade_id"),
                    valued_book_id=valuation.get("book_id"),
                    current_book_id=str(active_trade.book_id),
                )
                return VALUATION_PERSIST_BLOCKED
            latest_time = (
                session.query(func.max(Valuation.valuation_time))
                .filter(Valuation.trade_id == active_trade.trade_id)
                .scalar()
            )
            if latest_time is not None and (
                now - latest_time
            ).total_seconds() < VALUATION_WRITE_INTERVAL_SECONDS:
                return VALUATION_THROTTLED
            session.add(
                Valuation(
                    valuation_id=uuid.uuid4(),
                    trade_id=uuid.UUID(valuation["trade_id"]),
                    book_id=uuid.UUID(valuation["book_id"]),
                    asset_class=valuation["asset_class"],
                    valuation_time=now,
                    fair_value=valuation["fair_value"],
                    market_value=valuation.get("market_value"),
                    unrealized_pnl=valuation["unrealized_pnl"],
                    realized_pnl=valuation["realized_pnl"],
                    total_pnl=valuation["total_pnl"],
                    currency=valuation["currency"],
                    market_data_provider=valuation.get("market_data_provider"),
                    market_data_timestamp=_parse_timestamp(
                        valuation.get("market_data_timestamp")
                    ),
                    valuation_payload=valuation.get("valuation_payload"),
                    created_at=now,
                )
            )
            write_audit(
                SERVICE_NAME,
                "VALUATION_UPDATED",
                "Sampled valuation persisted",
                entity_type="TRADE",
                entity_id=valuation["trade_id"],
                payload={
                    "fair_value": str(valuation["fair_value"]),
                    "unrealized_pnl": str(valuation["unrealized_pnl"]),
                    "currency": valuation["currency"],
                    "market_data_provider": valuation.get("market_data_provider"),
                    "market_data_timestamp": valuation.get("market_data_timestamp"),
                    "write_interval_seconds": VALUATION_WRITE_INTERVAL_SECONDS,
                },
                session=session,
            )
        return VALUATION_PERSISTED
    except Exception:
        log.exception("valuation_persist_failed", trade_id=valuation.get("trade_id"))
        return VALUATION_PERSIST_BLOCKED


def load_terminal_valuations():
    """Restore the latest durable final valuation for every finalized closed trade."""
    with session_scope() as session:
        latest_time = (
            session.query(
                Valuation.trade_id.label("trade_id"),
                func.max(Valuation.valuation_time).label("valuation_time"),
            )
            .join(Trade, Trade.trade_id == Valuation.trade_id)
            .filter(
                Trade.status == "CLOSED",
                Trade.valuation_finalized.is_(True),
                Valuation.valuation_payload["final"].as_boolean().is_(True),
            )
            .group_by(Valuation.trade_id)
            .subquery()
        )
        rows = (
            session.query(Valuation, Trade, Book.name)
            .join(
                latest_time,
                and_(
                    latest_time.c.trade_id == Valuation.trade_id,
                    latest_time.c.valuation_time == Valuation.valuation_time,
                ),
            )
            .join(Trade, Trade.trade_id == Valuation.trade_id)
            .join(Book, Book.book_id == Trade.book_id)
            .all()
        )

        restored = []
        for valuation, trade, book_name in rows:
            restored.append({
                "trade_id": str(trade.trade_id),
                "book_id": str(trade.book_id),
                "book_name": book_name,
                "asset_class": trade.asset_class,
                "symbol": trade.symbol,
                "currency": valuation.currency,
                "quantity": signed_quantity(trade.side, trade.quantity),
                "trade_price": trade.trade_price,
                "fair_value": valuation.fair_value,
                "market_value": valuation.market_value,
                "unrealized_pnl": valuation.unrealized_pnl,
                "realized_pnl": valuation.realized_pnl,
                "total_pnl": valuation.total_pnl,
                "market_data_provider": valuation.market_data_provider,
                "market_data_timestamp": (
                    valuation.market_data_timestamp.isoformat()
                    if valuation.market_data_timestamp is not None else None
                ),
                "valuation_time": valuation.valuation_time.isoformat(),
                "valuation_payload": valuation.valuation_payload or {},
            })
    return restored


def finalize_closed_trades():
    """Persist exactly one terminal valuation for each not-yet-finalized close."""
    finals = []
    with session_scope() as session:
        rows = (
            _trades_with_book(session)
            .filter(Trade.status == "CLOSED", Trade.valuation_finalized.is_(False))
            .all()
        )
        for trade, book_name in rows:
            metadata = trade.trade_metadata or {}
            quantity = trade.quantity
            trade_price = trade.trade_price
            multiplier = int(metadata.get("multiplier", 1))
            valuation_provider = trade.market_data_provider or metadata.get(
                "discount_curve_provider"
            )
            curve_provenance = {
                field: metadata[field]
                for field in CURVE_PROVENANCE_FIELDS
                if metadata.get(field) is not None
            }

            if trade.close_price is not None:
                close_price = trade.close_price
                if trade.side == "SELL":
                    realized = (trade_price - close_price) * quantity * multiplier
                else:
                    realized = (close_price - trade_price) * quantity * multiplier
                fair_value = close_price * quantity * multiplier
                payload = {
                    "close_price": str(close_price),
                    "multiplier": multiplier,
                    "final": True,
                    **curve_provenance,
                }
            else:
                # A bulk presentation close has no executable close price. Freeze the
                # most recent mark so it still produces one terminal PnL observation.
                last = (
                    session.query(Valuation)
                    .filter(Valuation.trade_id == trade.trade_id)
                    .order_by(Valuation.valuation_time.desc())
                    .first()
                )
                if last is not None:
                    realized = last.unrealized_pnl
                    fair_value = last.fair_value
                else:
                    realized = Decimal("0")
                    fair_value = trade_price * quantity * multiplier
                payload = {
                    "close_price": None,
                    "multiplier": multiplier,
                    "final": True,
                    "marked_at_market": True,
                    **curve_provenance,
                }

            valuation = {
                "trade_id": str(trade.trade_id),
                "book_id": str(trade.book_id),
                "book_name": book_name,
                "asset_class": trade.asset_class,
                "symbol": trade.symbol,
                "currency": trade.trade_currency,
                "quantity": signed_quantity(trade.side, quantity),
                "trade_price": trade_price,
                "fair_value": fair_value,
                "market_value": fair_value,
                "unrealized_pnl": Decimal("0"),
                "realized_pnl": realized,
                "total_pnl": realized,
                "market_data_provider": valuation_provider,
                "market_data_timestamp": (
                    trade.close_price_timestamp.isoformat()
                    if trade.close_price_timestamp is not None
                    else None
                ),
                "valuation_time": get_iso_timestamp(),
                "valuation_payload": payload,
            }
            session.add(
                Valuation(
                    valuation_id=uuid.uuid4(),
                    trade_id=trade.trade_id,
                    book_id=trade.book_id,
                    asset_class=trade.asset_class,
                    valuation_time=utcnow(),
                    fair_value=fair_value,
                    market_value=fair_value,
                    unrealized_pnl=Decimal("0"),
                    realized_pnl=realized,
                    total_pnl=realized,
                    currency=trade.trade_currency,
                    market_data_provider=valuation_provider,
                    market_data_timestamp=trade.close_price_timestamp,
                    valuation_payload=payload,
                    created_at=utcnow(),
                )
            )
            trade.valuation_finalized = True
            log.info(
                "trade_finalized",
                trade_id=str(trade.trade_id),
                symbol=trade.symbol,
                realized_pnl=str(realized),
                close_price=(
                    str(trade.close_price) if trade.close_price is not None else None
                ),
            )
            finals.append(valuation)

    return finals
