"""Drop extra CHECK constraints on instruments.

Revision ID: c7a1e3b9d024
Revises: e2d4a6b8c019
"""

from alembic import op

revision = "c7a1e3b9d024"
down_revision = "e2d4a6b8c019"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE instruments DROP CONSTRAINT IF EXISTS ck_instruments_not_self_underlying")
    op.execute("ALTER TABLE instruments DROP CONSTRAINT IF EXISTS ck_instruments_terms_object")
    op.execute("ALTER TABLE instruments DROP CONSTRAINT IF EXISTS ck_instruments_underlying_required")


def downgrade():
    raise RuntimeError("Recreate the development database to return to the previous schema.")
