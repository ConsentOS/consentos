"""IAB Global Vendor List cache tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-06

Local cache of the canonical IAB GVL fetched from
``vendor-list.consensu.org/v3/vendor-list.json`` by a daily Celery
beat task (CMP-68). The schema mirrors the v3 GVL JSON shape so the
fetcher can upsert without a translation step.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp_columns() -> list[sa.Column]:
    """Standard ``created_at`` / ``updated_at`` pair used by all GVL tables."""
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "iab_gvl_meta",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("gvl_specification_version", sa.Integer, nullable=False),
        sa.Column("vendor_list_version", sa.Integer, nullable=False),
        sa.Column("tcf_policy_version", sa.Integer, nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamp_columns(),
    )

    for table in (
        "iab_purposes",
        "iab_special_purposes",
        "iab_features",
        "iab_special_features",
    ):
        op.create_table(
            table,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.Text, nullable=False),
            sa.Column("description", sa.Text, nullable=False),
            sa.Column("illustrations", postgresql.JSONB, nullable=True),
            *_timestamp_columns(),
        )

    op.create_table(
        "iab_data_categories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        *_timestamp_columns(),
    )

    op.create_table(
        "iab_vendors",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("purposes", postgresql.JSONB, nullable=True),
        sa.Column("leg_int_purposes", postgresql.JSONB, nullable=True),
        sa.Column("flexible_purposes", postgresql.JSONB, nullable=True),
        sa.Column("special_purposes", postgresql.JSONB, nullable=True),
        sa.Column("features", postgresql.JSONB, nullable=True),
        sa.Column("special_features", postgresql.JSONB, nullable=True),
        sa.Column("policy_url", sa.Text, nullable=True),
        sa.Column("deleted_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uses_cookies", sa.Boolean, nullable=True),
        sa.Column("cookie_refresh", sa.Boolean, nullable=True),
        sa.Column("uses_non_cookie_access", sa.Boolean, nullable=True),
        sa.Column("cookie_max_age_seconds", sa.Integer, nullable=True),
        sa.Column("data_retention", postgresql.JSONB, nullable=True),
        sa.Column("urls", postgresql.JSONB, nullable=True),
        sa.Column("data_declaration", postgresql.JSONB, nullable=True),
        *_timestamp_columns(),
    )
    op.create_index(
        "ix_iab_vendors_deleted_date",
        "iab_vendors",
        ["deleted_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_iab_vendors_deleted_date", table_name="iab_vendors")
    op.drop_table("iab_vendors")
    op.drop_table("iab_data_categories")
    op.drop_table("iab_special_features")
    op.drop_table("iab_features")
    op.drop_table("iab_special_purposes")
    op.drop_table("iab_purposes")
    op.drop_table("iab_gvl_meta")
