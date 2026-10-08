"""add is_superuser flag to users

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-08

Marks platform admins: operators allowed to edit the shared known
cookies list. Defaults to false for every existing user; grant it with
``python -m src.cli.platform_admin --email <address>``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_superuser",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_superuser")
