"""phase 5 curve provenance and instrument identity fields

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


def upgrade() -> None:
    op.add_column('watchlist_items', sa.Column('name', sa.Text(), nullable=True))
    op.add_column('watchlist_items', sa.Column('market', sa.Text(), nullable=True))
    op.add_column('market_data_curves',
                  sa.Column('curve_basis', sa.Text(), nullable=False))
    op.add_column('market_data_curves',
                  sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()),
                            nullable=False))


def downgrade() -> None:
    op.drop_column('market_data_curves', 'raw_payload')
    op.drop_column('market_data_curves', 'curve_basis')
    op.drop_column('watchlist_items', 'market')
    op.drop_column('watchlist_items', 'name')
