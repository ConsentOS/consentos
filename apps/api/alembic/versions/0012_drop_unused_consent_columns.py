"""drop unused columns from consent_records

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-09

Removes two unused columns and their index. Downgrade restores them
empty.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_consent_records_ab_test_id", table_name="consent_records", if_exists=True)
    op.drop_column("consent_records", "ab_variant_id")
    op.drop_column("consent_records", "ab_test_id")


def downgrade() -> None:
    op.add_column("consent_records", sa.Column("ab_test_id", sa.UUID(), nullable=True))
    op.add_column("consent_records", sa.Column("ab_variant_id", sa.UUID(), nullable=True))
    op.create_index("ix_consent_records_ab_test_id", "consent_records", ["ab_test_id"])
