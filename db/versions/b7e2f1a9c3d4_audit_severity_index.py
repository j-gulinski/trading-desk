"""audit severity partial index

Partial index on audit_logs(created_at) restricted to WARNING/ERROR/CRITICAL rows.
Serves the monitoring /audits feed for the System Overview "Errors & Warnings"
panel (filter by severity, order by created_at desc). Partial so it stays tiny:
it indexes only the rare non-INFO rows, not the ~5/s TRADE_CREATED/CLOSED traffic.

Deliberate exception to the end-of-project Alembic deferral (see docs/frontend-plan.md):
this is the one index the errors slice needs.

Revision ID: b7e2f1a9c3d4
Revises: d19af2df2449
Create Date: 2026-07-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2f1a9c3d4'
down_revision: Union[str, Sequence[str], None] = 'd19af2df2449'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        'ix_audit_logs_severity_recent',
        'audit_logs',
        ['created_at'],
        unique=False,
        postgresql_where=sa.text("severity IN ('WARNING', 'ERROR', 'CRITICAL')"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_audit_logs_severity_recent', table_name='audit_logs')
