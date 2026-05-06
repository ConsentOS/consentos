"""disclosed_vendor_ids cascade — site / group / org configs

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-06

Adds a ``disclosed_vendor_ids`` JSONB column to the three config
tables that participate in the org → group → site cascade. The
banner reads the resolved value and feeds it into the TCF v2.3
DisclosedVendors segment so the encoder emits real vendor IDs
rather than an empty disclosure set.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLES = ("site_configs", "site_group_configs", "org_configs")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("disclosed_vendor_ids", postgresql.JSONB, nullable=True),
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "disclosed_vendor_ids")
