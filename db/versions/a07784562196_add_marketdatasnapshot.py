"""add MarketDataSnapshot

Revision ID: a07784562196
Revises: 8b5da65b5cdf
Create Date: 2026-05-31 17:29:03.004865

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a07784562196'
down_revision: Union[str, Sequence[str], None] = '8b5da65b5cdf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_data_snapshots",
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", sa.BigInteger(), nullable=True),
        sa.Column("snapshot_type", sa.Text(), nullable=False),
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("market_data_snapshots")
