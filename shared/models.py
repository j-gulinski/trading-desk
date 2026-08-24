from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
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
    close_price_timestamp = Column(DateTime(timezone=True), nullable=True)
    close_snapshot_id = Column(
        UUID(as_uuid=True), ForeignKey("market_data_snapshots.snapshot_id"), nullable=True
    )
    close_reason = Column(Text, nullable=True)
    source = Column(Text, nullable=False)
    client_request_id = Column(Text, nullable=True, unique=True)
    valuation_finalized = Column(Boolean, nullable=False, server_default="FALSE")
    market_data_provider = Column(Text, nullable=True)
    entry_price_timestamp = Column(DateTime(timezone=True), nullable=True)
    entry_snapshot_id = Column(
        UUID(as_uuid=True), ForeignKey("market_data_snapshots.snapshot_id"), nullable=True
    )
    client_seen_price = Column(Numeric, nullable=True)
    created_by_service = Column(Text, nullable=True)
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
    market_data_provider = Column(Text, nullable=True)
    market_data_timestamp = Column(DateTime(timezone=True), nullable=True)
    valuation_payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)


class MarketDataSpotPrice(Base):
    __tablename__ = "market_data_spot_prices"
    __table_args__ = (
        UniqueConstraint(
            "provider", "symbol", name="uq_market_data_spot_prices_provider_symbol"
        ),
    )

    market_data_id = Column(UUID(as_uuid=True), primary_key=True)
    provider = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    asset_class = Column(Text, nullable=False)
    currency = Column(Text, nullable=True)
    bid = Column(Numeric, nullable=True)
    ask = Column(Numeric, nullable=True)
    last = Column(Numeric, nullable=True)
    mid = Column(Numeric, nullable=False)
    price_basis = Column(Text, nullable=False)
    quote_grade = Column(Text, nullable=False)
    previous_close = Column(Numeric, nullable=True)
    day_open = Column(Numeric, nullable=True)
    day_high = Column(Numeric, nullable=True)
    day_low = Column(Numeric, nullable=True)
    week52_high = Column(Numeric, nullable=True)
    week52_low = Column(Numeric, nullable=True)
    volume = Column(Numeric, nullable=True)
    average_volume = Column(Numeric, nullable=True)
    provider_timestamp = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False)
    stale_after_seconds = Column(Integer, nullable=True)
    closed_stale_after_seconds = Column(Integer, nullable=True)
    market_open = Column(Boolean, nullable=True)
    latest_snapshot_id = Column(
        UUID(as_uuid=True), ForeignKey("market_data_snapshots.snapshot_id"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), nullable=False)


class MarketDataSnapshot(Base):
    __tablename__ = "market_data_snapshots"
    __table_args__ = (
        Index(
            "ix_market_data_snapshots_provider_symbol_received_at",
            "provider",
            "symbol",
            "received_at",
        ),
    )

    snapshot_id = Column(UUID(as_uuid=True), primary_key=True)
    provider = Column(Text, nullable=False)
    symbol = Column(Text, nullable=False)
    asset_class = Column(Text, nullable=False)
    currency = Column(Text, nullable=True)
    bid = Column(Numeric, nullable=True)
    ask = Column(Numeric, nullable=True)
    last = Column(Numeric, nullable=True)
    mid = Column(Numeric, nullable=False)
    price_basis = Column(Text, nullable=False)
    quote_grade = Column(Text, nullable=False)
    provider_timestamp = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    raw_payload = Column(JSONB, nullable=False)


class MarketDataCurve(Base):
    __tablename__ = "market_data_curves"
    __table_args__ = (
        UniqueConstraint(
            "provider", "curve_name", "as_of_date",
            name="uq_market_data_curves_provider_curve_as_of",
        ),
    )

    curve_id = Column(UUID(as_uuid=True), primary_key=True)
    provider = Column(Text, nullable=False)
    curve_name = Column(Text, nullable=False)
    curve_type = Column(Text, nullable=False)
    currency = Column(Text, nullable=False)
    index_tenor = Column(Text, nullable=True)
    as_of_date = Column(Date, nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    raw_payload = Column(JSONB, nullable=False)


class MarketDataCurvePoint(Base):
    __tablename__ = "market_data_curve_points"
    __table_args__ = (
        UniqueConstraint(
            "curve_id", "tenor_label", name="uq_market_data_curve_points_curve_tenor"
        ),
    )

    curve_point_id = Column(UUID(as_uuid=True), primary_key=True)
    curve_id = Column(
        UUID(as_uuid=True),
        ForeignKey("market_data_curves.curve_id", ondelete="CASCADE"),
        nullable=False,
    )
    tenor_label = Column(Text, nullable=False)
    tenor_years = Column(Numeric, nullable=False)
    rate = Column(Numeric, nullable=False)
    source_series = Column(Text, nullable=True)
    source_as_of = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    symbol = Column(Text, primary_key=True)
    asset_class = Column(Text, nullable=False)
    currency = Column(Text, nullable=False)
    providers = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)


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
