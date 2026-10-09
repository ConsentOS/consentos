"""drop an unused column from organisations

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-09

Removes an unused column. Downgrade restores it with its original
default.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("organisations", "billing_plan")


def downgrade() -> None:
    op.add_column(
        "organisations",
        sa.Column("billing_plan", sa.String(length=50), server_default="free", nullable=False),
    )
