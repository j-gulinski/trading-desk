"""Baseline schema built from desk_domain.models."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('audit_logs',
    sa.Column('audit_id', sa.UUID(), nullable=False),
    sa.Column('service_name', sa.Text(), nullable=False),
    sa.Column('event_type', sa.Text(), nullable=False),
    sa.Column('entity_type', sa.Text(), nullable=True),
    sa.Column('entity_id', sa.Text(), nullable=True),
    sa.Column('correlation_id', sa.Text(), nullable=True),
    sa.Column('severity', sa.Text(), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('audit_id')
    )
    op.create_index('ix_audit_logs_entity_id', 'audit_logs', ['entity_id'], unique=False)
    op.create_index('ix_audit_logs_severity_recent', 'audit_logs', ['created_at'], unique=False, postgresql_where=sa.text("severity IN ('WARNING', 'ERROR', 'CRITICAL')"))
    op.create_table('books',
    sa.Column('book_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('expected_asset_class', sa.Text(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='TRUE', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('book_id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('instruments',
    sa.Column('instrument_id', sa.UUID(), nullable=False),
    sa.Column('symbol', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=True),
    sa.Column('asset_class', sa.Text(), nullable=False),
    sa.Column('currency', sa.Text(), nullable=False),
    sa.Column('market', sa.Text(), nullable=True),
    sa.Column('terms', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('underlying_instrument_id', sa.UUID(), nullable=True),
    sa.Column('retired_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['underlying_instrument_id'], ['instruments.instrument_id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('instrument_id'),
    sa.UniqueConstraint('symbol')
    )
    op.create_index('ix_instruments_asset_class', 'instruments', ['asset_class'], unique=False)
    op.create_index('ix_instruments_underlying_instrument_id', 'instruments', ['underlying_instrument_id'], unique=False)
    op.create_table('market_data_curves',
    sa.Column('curve_id', sa.UUID(), nullable=False),
    sa.Column('provider', sa.Text(), nullable=False),
    sa.Column('curve_name', sa.Text(), nullable=False),
    sa.Column('curve_basis', sa.Text(), nullable=False),
    sa.Column('currency', sa.Text(), nullable=False),
    sa.Column('index_tenor', sa.Text(), nullable=True),
    sa.Column('as_of_date', sa.Date(), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.PrimaryKeyConstraint('curve_id'),
    sa.UniqueConstraint('provider', 'curve_name', 'as_of_date', name='uq_market_data_curves_provider_curve_as_of')
    )
    op.create_table('market_data_snapshots',
    sa.Column('snapshot_id', sa.UUID(), nullable=False),
    sa.Column('provider', sa.Text(), nullable=False),
    sa.Column('symbol', sa.Text(), nullable=False),
    sa.Column('asset_class', sa.Text(), nullable=False),
    sa.Column('currency', sa.Text(), nullable=True),
    sa.Column('bid', sa.Numeric(), nullable=True),
    sa.Column('ask', sa.Numeric(), nullable=True),
    sa.Column('last', sa.Numeric(), nullable=True),
    sa.Column('mid', sa.Numeric(), nullable=False),
    sa.Column('price_basis', sa.Text(), nullable=False),
    sa.Column('quote_grade', sa.Text(), nullable=False),
    sa.Column('provider_timestamp', sa.DateTime(timezone=True), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.PrimaryKeyConstraint('snapshot_id')
    )
    op.create_index('ix_market_data_snapshots_provider_symbol_received_at', 'market_data_snapshots', ['provider', 'symbol', 'received_at'], unique=False)
    op.create_table('provider_request_ledgers',
    sa.Column('provider', sa.Text(), nullable=False),
    sa.Column('usage_date', sa.Date(), nullable=False),
    sa.Column('requests', sa.Integer(), server_default='0', nullable=False),
    sa.Column('credits', sa.Integer(), server_default='0', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('provider', 'usage_date')
    )
    op.create_table('market_data_curve_points',
    sa.Column('curve_point_id', sa.UUID(), nullable=False),
    sa.Column('curve_id', sa.UUID(), nullable=False),
    sa.Column('tenor_label', sa.Text(), nullable=False),
    sa.Column('tenor_years', sa.Numeric(), nullable=False),
    sa.Column('rate', sa.Numeric(), nullable=False),
    sa.Column('source_series', sa.Text(), nullable=True),
    sa.Column('source_as_of', sa.Date(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['curve_id'], ['market_data_curves.curve_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('curve_point_id'),
    sa.UniqueConstraint('curve_id', 'tenor_label', name='uq_market_data_curve_points_curve_tenor')
    )
    op.create_table('market_data_spot_prices',
    sa.Column('market_data_id', sa.UUID(), nullable=False),
    sa.Column('provider', sa.Text(), nullable=False),
    sa.Column('symbol', sa.Text(), nullable=False),
    sa.Column('asset_class', sa.Text(), nullable=False),
    sa.Column('currency', sa.Text(), nullable=True),
    sa.Column('bid', sa.Numeric(), nullable=True),
    sa.Column('ask', sa.Numeric(), nullable=True),
    sa.Column('last', sa.Numeric(), nullable=True),
    sa.Column('mid', sa.Numeric(), nullable=False),
    sa.Column('price_basis', sa.Text(), nullable=False),
    sa.Column('quote_grade', sa.Text(), nullable=False),
    sa.Column('previous_close', sa.Numeric(), nullable=True),
    sa.Column('provider_timestamp', sa.DateTime(timezone=True), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('stale_after_seconds', sa.Integer(), nullable=True),
    sa.Column('closed_stale_after_seconds', sa.Integer(), nullable=True),
    sa.Column('market_open', sa.Boolean(), nullable=True),
    sa.Column('latest_snapshot_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['latest_snapshot_id'], ['market_data_snapshots.snapshot_id'], ),
    sa.PrimaryKeyConstraint('market_data_id'),
    sa.UniqueConstraint('provider', 'symbol', name='uq_market_data_spot_prices_provider_symbol')
    )
    op.create_table('trades',
    sa.Column('trade_id', sa.UUID(), nullable=False),
    sa.Column('book_id', sa.UUID(), nullable=False),
    sa.Column('instrument_id', sa.UUID(), nullable=False),
    sa.Column('side', sa.Text(), nullable=False),
    sa.Column('quantity', sa.Numeric(), nullable=False),
    sa.Column('trade_price', sa.Numeric(), nullable=False),
    sa.Column('trade_currency', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('close_price', sa.Numeric(), nullable=True),
    sa.Column('close_price_timestamp', sa.DateTime(timezone=True), nullable=True),
    sa.Column('close_snapshot_id', sa.UUID(), nullable=True),
    sa.Column('close_reason', sa.Text(), nullable=True),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('client_request_id', sa.Text(), nullable=True),
    sa.Column('valuation_finalized', sa.Boolean(), server_default='FALSE', nullable=False),
    sa.Column('market_data_provider', sa.Text(), nullable=True),
    sa.Column('entry_price_timestamp', sa.DateTime(timezone=True), nullable=True),
    sa.Column('entry_snapshot_id', sa.UUID(), nullable=True),
    sa.Column('client_seen_price', sa.Numeric(), nullable=True),
    sa.Column('created_by_service', sa.Text(), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['book_id'], ['books.book_id'], ),
    sa.ForeignKeyConstraint(['close_snapshot_id'], ['market_data_snapshots.snapshot_id'], ),
    sa.ForeignKeyConstraint(['entry_snapshot_id'], ['market_data_snapshots.snapshot_id'], ),
    sa.ForeignKeyConstraint(['instrument_id'], ['instruments.instrument_id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('trade_id'),
    sa.UniqueConstraint('client_request_id')
    )
    op.create_index('ix_trades_book_id', 'trades', ['book_id'], unique=False)
    op.create_index('ix_trades_instrument_id', 'trades', ['instrument_id'], unique=False)
    op.create_index('ix_trades_status', 'trades', ['status'], unique=False)
    op.create_table('watchlist_items',
    sa.Column('instrument_id', sa.UUID(), nullable=False),
    sa.Column('providers', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['instrument_id'], ['instruments.instrument_id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('instrument_id')
    )
    op.create_table('valuations',
    sa.Column('valuation_id', sa.UUID(), nullable=False),
    sa.Column('trade_id', sa.UUID(), nullable=False),
    sa.Column('valuation_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('fair_value', sa.Numeric(), nullable=False),
    sa.Column('unrealized_pnl', sa.Numeric(), server_default='0', nullable=False),
    sa.Column('realized_pnl', sa.Numeric(), server_default='0', nullable=False),
    sa.Column('total_pnl', sa.Numeric(), server_default='0', nullable=False),
    sa.Column('currency', sa.Text(), nullable=False),
    sa.Column('market_data_provider', sa.Text(), nullable=True),
    sa.Column('market_data_timestamp', sa.DateTime(timezone=True), nullable=True),
    sa.Column('valuation_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['trade_id'], ['trades.trade_id'], ),
    sa.PrimaryKeyConstraint('valuation_id')
    )
    op.create_index('ix_valuations_trade_id_time', 'valuations', ['trade_id', 'valuation_time'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_valuations_trade_id_time', table_name='valuations')
    op.drop_table('valuations')
    op.drop_table('watchlist_items')
    op.drop_index('ix_trades_status', table_name='trades')
    op.drop_index('ix_trades_instrument_id', table_name='trades')
    op.drop_index('ix_trades_book_id', table_name='trades')
    op.drop_table('trades')
    op.drop_table('market_data_spot_prices')
    op.drop_table('market_data_curve_points')
    op.drop_table('provider_request_ledgers')
    op.drop_index('ix_market_data_snapshots_provider_symbol_received_at', table_name='market_data_snapshots')
    op.drop_table('market_data_snapshots')
    op.drop_table('market_data_curves')
    op.drop_index('ix_instruments_underlying_instrument_id', table_name='instruments')
    op.drop_index('ix_instruments_asset_class', table_name='instruments')
    op.drop_table('instruments')
    op.drop_table('books')
    op.drop_index('ix_audit_logs_severity_recent', table_name='audit_logs', postgresql_where=sa.text("severity IN ('WARNING', 'ERROR', 'CRITICAL')"))
    op.drop_index('ix_audit_logs_entity_id', table_name='audit_logs')
    op.drop_table('audit_logs')
