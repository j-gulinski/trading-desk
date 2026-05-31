"""add MarketDataSpotPrices

Revision ID: f3887497625d
Revises: 4668f53bd64b
Create Date: 2026-05-31 17:29:15.069741

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f3887497625d'
down_revision: Union[str, Sequence[str], None] = '4668f53bd64b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_data_spot_prices",
        sa.Column("market_data_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", sa.BigInteger(), nullable=True),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("asset_class", sa.Text(), nullable=False),
        sa.Column("bid", sa.Numeric(), nullable=True),
        sa.Column("ask", sa.Numeric(), nullable=True),
        sa.Column("mid", sa.Numeric(), nullable=True),
        sa.Column("last", sa.Numeric(), nullable=True),
        sa.Column("spot", sa.Numeric(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("'SIMULATED'")),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("market_data_spot_prices")
