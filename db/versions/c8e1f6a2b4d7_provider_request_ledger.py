"""add provider request ledger

Revision ID: c8e1f6a2b4d7
Revises: a9c4e5f61b27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8e1f6a2b4d7"
down_revision: Union[str, Sequence[str], None] = "a9c4e5f61b27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provider_request_ledgers",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("requests", sa.Integer(), server_default="0", nullable=False),
        sa.Column("credits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("provider", "usage_date"),
    )


def downgrade() -> None:
    op.drop_table("provider_request_ledgers")
