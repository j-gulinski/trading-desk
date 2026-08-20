"""provider market schema

Phase 1 reshape for the six-provider world (docs/implementation-roadmap.md §5–6). Drops and
recreates the market tables — the pre-fork rows are synthetic and a fresh DB is the
deployment path.

Revision ID: f4a8c1d27b3e
Revises: b7e2f1a9c3d4
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f4a8c1d27b3e'
down_revision: Union[str, Sequence[str], None] = 'b7e2f1a9c3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('market_data_spot_prices')
    op.drop_table('market_data_snapshots')
    op.drop_table('market_data_curves')

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
        sa.PrimaryKeyConstraint('market_data_id'),
        sa.UniqueConstraint('provider', 'symbol',
                            name='uq_market_data_spot_prices_provider_symbol'),
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
        sa.PrimaryKeyConstraint('snapshot_id'),
    )
    op.create_index('ix_market_data_snapshots_provider_symbol_received_at',
                    'market_data_snapshots', ['provider', 'symbol', 'received_at'])
    op.create_foreign_key(
        'fk_market_data_spot_prices_latest_snapshot_id', 'market_data_spot_prices',
        'market_data_snapshots', ['latest_snapshot_id'], ['snapshot_id'],
    )

    op.create_table('market_data_curves',
        sa.Column('curve_id', sa.UUID(), nullable=False),
        sa.Column('provider', sa.Text(), nullable=False),
        sa.Column('curve_name', sa.Text(), nullable=False),
        sa.Column('currency', sa.Text(), nullable=False),
        sa.Column('index_tenor', sa.Text(), nullable=True),
        sa.Column('as_of_date', sa.Date(), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('curve_id'),
        sa.UniqueConstraint('provider', 'curve_name', 'as_of_date',
                            name='uq_market_data_curves_provider_curve_as_of'),
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
        sa.PrimaryKeyConstraint('curve_point_id'),
        sa.ForeignKeyConstraint(['curve_id'], ['market_data_curves.curve_id'],
                                ondelete='CASCADE'),
        sa.UniqueConstraint('curve_id', 'tenor_label',
                            name='uq_market_data_curve_points_curve_tenor'),
    )

    op.create_table('watchlist_items',
        sa.Column('symbol', sa.Text(), nullable=False),
        sa.Column('asset_class', sa.Text(), nullable=False),
        sa.Column('currency', sa.Text(), nullable=False),
        sa.Column('providers', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('symbol'),
    )

    op.add_column('trades', sa.Column('market_data_provider', sa.Text(), nullable=True))
    op.add_column('trades',
                  sa.Column('entry_price_timestamp', sa.DateTime(timezone=True), nullable=True))
    op.add_column('trades', sa.Column('entry_snapshot_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_trades_entry_snapshot_id', 'trades', 'market_data_snapshots',
                          ['entry_snapshot_id'], ['snapshot_id'])
    op.add_column('trades', sa.Column('client_seen_price', sa.Numeric(), nullable=True))
    op.add_column('trades', sa.Column('created_by_service', sa.Text(), nullable=True))
    op.add_column('trades',
                  sa.Column('close_price_timestamp', sa.DateTime(timezone=True), nullable=True))
    op.add_column('trades', sa.Column('close_snapshot_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_trades_close_snapshot_id', 'trades', 'market_data_snapshots',
                          ['close_snapshot_id'], ['snapshot_id'])

    op.add_column('valuations', sa.Column('market_data_provider', sa.Text(), nullable=True))
    op.add_column('valuations',
                  sa.Column('market_data_timestamp', sa.DateTime(timezone=True), nullable=True))
    op.drop_column('valuations', 'market_data_reference')


def downgrade() -> None:
    op.add_column('valuations', sa.Column('market_data_reference', sa.Text(), nullable=True))
    op.drop_column('valuations', 'market_data_timestamp')
    op.drop_column('valuations', 'market_data_provider')

    op.drop_constraint('fk_trades_close_snapshot_id', 'trades', type_='foreignkey')
    op.drop_column('trades', 'close_snapshot_id')
    op.drop_column('trades', 'close_price_timestamp')
    op.drop_column('trades', 'created_by_service')
    op.drop_column('trades', 'client_seen_price')
    op.drop_constraint('fk_trades_entry_snapshot_id', 'trades', type_='foreignkey')
    op.drop_column('trades', 'entry_snapshot_id')
    op.drop_column('trades', 'entry_price_timestamp')
    op.drop_column('trades', 'market_data_provider')

    op.drop_table('watchlist_items')
    op.drop_table('market_data_curve_points')
    op.drop_table('market_data_curves')
    op.drop_constraint('fk_market_data_spot_prices_latest_snapshot_id',
                       'market_data_spot_prices', type_='foreignkey')
    op.drop_index('ix_market_data_snapshots_provider_symbol_received_at',
                  table_name='market_data_snapshots')
    op.drop_table('market_data_snapshots')
    op.drop_table('market_data_spot_prices')

    op.create_table('market_data_curves',
        sa.Column('curve_id', sa.UUID(), nullable=False),
        sa.Column('event_id', sa.BigInteger(), nullable=True),
        sa.Column('curve_name', sa.Text(), nullable=False),
        sa.Column('curve_type', sa.Text(), nullable=False),
        sa.Column('currency', sa.Text(), nullable=True),
        sa.Column('tenors', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('rates', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('event_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint('curve_id'),
    )
    op.create_table('market_data_snapshots',
        sa.Column('snapshot_id', sa.UUID(), nullable=False),
        sa.Column('event_id', sa.BigInteger(), nullable=True),
        sa.Column('snapshot_type', sa.Text(), nullable=False),
        sa.Column('snapshot_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint('snapshot_id'),
    )
    op.create_table('market_data_spot_prices',
        sa.Column('market_data_id', sa.UUID(), nullable=False),
        sa.Column('event_id', sa.BigInteger(), nullable=True),
        sa.Column('symbol', sa.Text(), nullable=False),
        sa.Column('asset_class', sa.Text(), nullable=False),
        sa.Column('bid', sa.Numeric(), nullable=True),
        sa.Column('ask', sa.Numeric(), nullable=True),
        sa.Column('mid', sa.Numeric(), nullable=True),
        sa.Column('last', sa.Numeric(), nullable=True),
        sa.Column('spot', sa.Numeric(), nullable=True),
        sa.Column('currency', sa.Text(), nullable=True),
        sa.Column('source', sa.Text(), server_default='SIMULATED', nullable=False),
        sa.Column('event_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint('market_data_id'),
    )
