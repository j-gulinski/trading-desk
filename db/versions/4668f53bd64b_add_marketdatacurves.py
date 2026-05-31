"""add MarketDataCurves

Revision ID: 4668f53bd64b
Revises: a07784562196
Create Date: 2026-05-31 17:29:08.224324

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '4668f53bd64b'
down_revision: Union[str, Sequence[str], None] = 'a07784562196'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_data_curves",
        sa.Column("curve_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", sa.BigInteger(), nullable=True),
        sa.Column("curve_name", sa.Text(), nullable=False),
        sa.Column("curve_type", sa.Text(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("tenors", postgresql.JSONB(), nullable=False),
        sa.Column("rates", postgresql.JSONB(), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("market_data_curves")
