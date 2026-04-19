"""consent_sharing_enabled on site_group_configs

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-19

When enabled, sites in the group participate in cross-domain consent
sharing via an iframe bridge on the API domain. The banner embeds a
hidden iframe that reads/writes a shared cookie so consent given on
one domain is automatically applied on another.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "site_group_configs",
        sa.Column("consent_sharing_enabled", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "site_group_configs",
        sa.Column("consent_bridge_url", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("site_group_configs", "consent_bridge_url")
    op.drop_column("site_group_configs", "consent_sharing_enabled")
