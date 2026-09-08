"""Separate instruments from watchlist membership and trades."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "e2d4a6b8c019"
down_revision = "c8e1f6a2b4d7"
branch_labels = None
depends_on = None


def upgrade():
    populated = op.get_bind().execute(sa.text("""
        SELECT EXISTS (SELECT 1 FROM trades UNION ALL SELECT 1 FROM watchlist_items)
    """)).scalar_one()
    if populated:
        raise RuntimeError("Recreate the development database before applying the instrument schema.")
    op.create_table(
        "instruments",
        sa.Column("instrument_id", sa.UUID(), primary_key=True),
        sa.Column("symbol", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text()),
        sa.Column("asset_class", sa.Text(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("market", sa.Text()),
        sa.Column("terms", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "underlying_instrument_id", sa.UUID(),
            sa.ForeignKey("instruments.instrument_id", ondelete="RESTRICT"),
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "underlying_instrument_id <> instrument_id",
            name="ck_instruments_not_self_underlying",
        ),
        sa.CheckConstraint("jsonb_typeof(terms) = 'object'", name="ck_instruments_terms_object"),
        sa.CheckConstraint(
            "(asset_class = 'EUROPEAN_OPTION') = (underlying_instrument_id IS NOT NULL)",
            name="ck_instruments_underlying_required",
        ),
    )
    op.drop_constraint("watchlist_items_pkey", "watchlist_items", type_="primary")
    for column in ("symbol", "name", "asset_class", "currency", "market"):
        op.drop_column("watchlist_items", column)
    op.add_column("watchlist_items", sa.Column("instrument_id", sa.UUID(), nullable=False))
    op.create_primary_key("watchlist_items_pkey", "watchlist_items", ["instrument_id"])
    op.create_foreign_key(
        "watchlist_items_instrument_id_fkey", "watchlist_items", "instruments",
        ["instrument_id"], ["instrument_id"], ondelete="RESTRICT",
    )
    for column in ("symbol", "asset_class", "trade_date", "instrument_id"):
        op.drop_column("trades", column)
    op.add_column("trades", sa.Column("instrument_id", sa.UUID(), nullable=False))
    op.create_foreign_key(
        "trades_instrument_id_fkey", "trades", "instruments",
        ["instrument_id"], ["instrument_id"], ondelete="RESTRICT",
    )
    for column in ("book_id", "asset_class", "market_value"):
        op.drop_column("valuations", column)
    op.create_index("ix_trades_instrument_id", "trades", ["instrument_id"])
    op.create_index("ix_instruments_underlying_instrument_id", "instruments", ["underlying_instrument_id"])
    op.create_index("ix_instruments_asset_class", "instruments", ["asset_class"])


def downgrade():
    raise RuntimeError("Recreate the development database to return to the previous schema.")
