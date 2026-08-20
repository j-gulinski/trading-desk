"""close quote provenance

Revision ID: c7d91a42e5f0
Revises: a1c4e8b70d92
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7d91a42e5f0"
down_revision: Union[str, Sequence[str], None] = "a1c4e8b70d92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trades",
        sa.Column("close_price_timestamp", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "trades",
        sa.Column("close_snapshot_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_trades_close_snapshot_id",
        "trades",
        "market_data_snapshots",
        ["close_snapshot_id"],
        ["snapshot_id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_trades_close_snapshot_id", "trades", type_="foreignkey")
    op.drop_column("trades", "close_snapshot_id")
    op.drop_column("trades", "close_price_timestamp")
