"""add Valuations

Revision ID: 8b5da65b5cdf
Revises: 996103f1960a
Create Date: 2026-05-31 17:28:57.965380

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '8b5da65b5cdf'
down_revision: Union[str, Sequence[str], None] = '996103f1960a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "valuations",
        sa.Column("valuation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trade_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_class", sa.Text(), nullable=False),
        sa.Column("valuation_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fair_value", sa.Numeric(), nullable=False),
        sa.Column("market_value", sa.Numeric(), nullable=True),
        sa.Column("unrealized_pnl", sa.Numeric(), nullable=False, server_default=sa.text("0")),
        sa.Column("realized_pnl", sa.Numeric(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_pnl", sa.Numeric(), nullable=False, server_default=sa.text("0")),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("market_data_reference", sa.Text(), nullable=True),
        sa.Column("valuation_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["trade_id"], ["trades.trade_id"], name="fk_valuations_trade_id"),
        sa.ForeignKeyConstraint(["book_id"], ["books.book_id"], name="fk_valuations_book_id"),
    )


def downgrade() -> None:
    op.drop_table("valuations")
