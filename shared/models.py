from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Book(Base):
    __tablename__ = "books"

    book_id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(Text, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    expected_asset_class = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="TRUE")
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    created_by = Column(Text, nullable=True)
    updated_by = Column(Text, nullable=True)


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trades_status", "status"),
        Index("ix_trades_book_id", "book_id"),
        Index("ix_trades_symbol", "symbol"),
        Index("ix_trades_asset_class", "asset_class"),
    )

    trade_id = Column(UUID(as_uuid=True), primary_key=True)
    book_id = Column(UUID(as_uuid=True), ForeignKey("books.book_id"), nullable=False)
    asset_class = Column(Text, nullable=False)
    instrument_id = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    side = Column(Text, nullable=False)
    quantity = Column(Numeric, nullable=False)
    trade_price = Column(Numeric, nullable=False)
    trade_currency = Column(Text, nullable=False)
    trade_date = Column(DateTime(timezone=True), nullable=False)
    status = Column(Text, nullable=False)
    opened_at = Column(DateTime(timezone=True), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    close_price = Column(Numeric, nullable=True)
    close_reason = Column(Text, nullable=True)
    source = Column(Text, nullable=False)
    client_request_id = Column(Text, nullable=True, unique=True)
    valuation_finalized = Column(Boolean, nullable=False, server_default="FALSE")
    trade_metadata = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class Valuation(Base):
    __tablename__ = "valuations"
    __table_args__ = (
        Index("ix_valuations_trade_id_time", "trade_id", "valuation_time"),
    )

    valuation_id = Column(UUID(as_uuid=True), primary_key=True)
    trade_id = Column(UUID(as_uuid=True), ForeignKey("trades.trade_id"), nullable=False)
    book_id = Column(UUID(as_uuid=True), ForeignKey("books.book_id"), nullable=False)
    asset_class = Column(Text, nullable=False)
    valuation_time = Column(DateTime(timezone=True), nullable=False)
    fair_value = Column(Numeric, nullable=False)
    market_value = Column(Numeric, nullable=True)
    unrealized_pnl = Column(Numeric, nullable=False, server_default="0")
    realized_pnl = Column(Numeric, nullable=False, server_default="0")
    total_pnl = Column(Numeric, nullable=False, server_default="0")
    currency = Column(Text, nullable=False)
    market_data_reference = Column(Text, nullable=True)
    valuation_payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)


class MarketDataSnapshot(Base):
    __tablename__ = "market_data_snapshots"

    snapshot_id = Column(UUID(as_uuid=True), primary_key=True)
    event_id = Column(BigInteger, nullable=True)
    snapshot_type = Column(Text, nullable=False)
    snapshot_time = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    payload = Column(JSONB, nullable=False)


class MarketDataCurve(Base):
    __tablename__ = "market_data_curves"

    curve_id = Column(UUID(as_uuid=True), primary_key=True)
    event_id = Column(BigInteger, nullable=True)
    curve_name = Column(Text, nullable=False)
    curve_type = Column(Text, nullable=False)
    currency = Column(Text, nullable=True)
    tenors = Column(JSONB, nullable=False)
    rates = Column(JSONB, nullable=False)
    event_time = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    raw_payload = Column(JSONB, nullable=False)


class MarketDataSpotPrice(Base):
    __tablename__ = "market_data_spot_prices"

    market_data_id = Column(UUID(as_uuid=True), primary_key=True)
    event_id = Column(BigInteger, nullable=True)
    symbol = Column(Text, nullable=False)
    asset_class = Column(Text, nullable=False)
    bid = Column(Numeric, nullable=True)
    ask = Column(Numeric, nullable=True)
    mid = Column(Numeric, nullable=True)
    last = Column(Numeric, nullable=True)
    spot = Column(Numeric, nullable=True)
    currency = Column(Text, nullable=True)
    source = Column(Text, nullable=False, server_default="'SIMULATED'")
    event_time = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    raw_payload = Column(JSONB, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        # /trades/<id>/audit-logs lookups by entity id
        Index("ix_audit_logs_entity_id", "entity_id"),
        Index(
            "ix_audit_logs_severity_recent",
            "created_at",
            postgresql_where=text("severity IN ('WARNING', 'ERROR', 'CRITICAL')"),
        ),
    )

    audit_id = Column(UUID(as_uuid=True), primary_key=True)
    service_name = Column(Text, nullable=False)
    event_type = Column(Text, nullable=False)
    entity_type = Column(Text, nullable=True)
    entity_id = Column(Text, nullable=True)
    correlation_id = Column(Text, nullable=True)
    severity = Column(Text, nullable=False)
    message = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
