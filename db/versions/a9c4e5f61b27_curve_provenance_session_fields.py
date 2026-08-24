"""curve provenance and session fields

Phase 5: curve sets retain their raw source response and a curve_type label; the spot
board gains nullable session fields the quote responses already carry (D35). Both curve
columns are NOT NULL without defaults — nothing writes market_data_curves before this
revision, so the table is empty by construction.

Revision ID: a9c4e5f61b27
Revises: f4a8c1d27b3e
Create Date: 2026-08-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a9c4e5f61b27'
down_revision: Union[str, Sequence[str], None] = 'f4a8c1d27b3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SESSION_COLUMNS = (
    'day_open',
    'day_high',
    'day_low',
    'week52_high',
    'week52_low',
    'volume',
    'average_volume',
)


def upgrade() -> None:
    op.add_column('market_data_curves',
                  sa.Column('curve_type', sa.Text(), nullable=False))
    op.add_column('market_data_curves',
                  sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()),
                            nullable=False))
    for column in SESSION_COLUMNS:
        op.add_column('market_data_spot_prices',
                      sa.Column(column, sa.Numeric(), nullable=True))


def downgrade() -> None:
    for column in reversed(SESSION_COLUMNS):
        op.drop_column('market_data_spot_prices', column)
    op.drop_column('market_data_curves', 'raw_payload')
    op.drop_column('market_data_curves', 'curve_type')
