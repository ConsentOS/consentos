"""enabled_categories on site / group / org configs

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-14

Per-site control over which cookie categories the banner displays.
Cascades the same way every other config setting does — site overrides
site-group overrides org overrides system default (all 5 categories).

Stored as JSONB rather than an array column so the resolver sees a
plain Python list via SQLAlchemy's JSONB codec and doesn't need
PostgreSQL-specific array handling in the merge logic.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLES = ("site_configs", "site_group_configs", "org_configs")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "enabled_categories",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "enabled_categories")
