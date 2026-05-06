"""widen iab_vendors.cookie_max_age_seconds to BigInteger

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-06

The IAB GVL contains vendors with ``cookieMaxAgeSeconds`` values
exceeding the int32 limit (e.g. 63072000000 — effectively "forever"
cookies). Postgres asyncpg rejects them at insert time. Widening the
column to BigInteger so the upstream values fit.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "iab_vendors",
        "cookie_max_age_seconds",
        type_=sa.BigInteger(),
        existing_type=sa.Integer(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "iab_vendors",
        "cookie_max_age_seconds",
        type_=sa.Integer(),
        existing_type=sa.BigInteger(),
        existing_nullable=True,
    )
