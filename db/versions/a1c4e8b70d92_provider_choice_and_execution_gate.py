"""provider watchlist choice and current quote state

Revision ID: a1c4e8b70d92
Revises: f4a8c1d27b3e
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1c4e8b70d92'
down_revision: Union[str, Sequence[str], None] = 'f4a8c1d27b3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('watchlist_items', 'capabilities', new_column_name='providers')
    op.execute("""
        UPDATE watchlist_items
           SET providers = COALESCE(
                 (SELECT jsonb_object_agg(key, value)
                    FROM jsonb_each(providers)
                   WHERE value = 'true'::jsonb),
                 '{}'::jsonb)
         WHERE providers IS NOT NULL
    """)

    op.add_column('market_data_spot_prices',
                  sa.Column('stale_after_seconds', sa.Integer(), nullable=True))
    op.add_column('market_data_spot_prices',
                  sa.Column('closed_stale_after_seconds', sa.Integer(), nullable=True))
    op.add_column('market_data_spot_prices',
                  sa.Column('market_open', sa.Boolean(), nullable=True))
    op.add_column('market_data_spot_prices',
                  sa.Column('previous_close', sa.Numeric(), nullable=True))
    op.add_column('market_data_spot_prices',
                  sa.Column('latest_snapshot_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_market_data_spot_prices_latest_snapshot_id', 'market_data_spot_prices',
        'market_data_snapshots', ['latest_snapshot_id'], ['snapshot_id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_market_data_spot_prices_latest_snapshot_id',
                       'market_data_spot_prices', type_='foreignkey')
    op.drop_column('market_data_spot_prices', 'latest_snapshot_id')
    op.drop_column('market_data_spot_prices', 'previous_close')
    op.drop_column('market_data_spot_prices', 'market_open')
    op.drop_column('market_data_spot_prices', 'closed_stale_after_seconds')
    op.drop_column('market_data_spot_prices', 'stale_after_seconds')
    op.alter_column('watchlist_items', 'providers', new_column_name='capabilities')
