"""add org and site group level translations

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-27

Extends the translation cascade above the per-site ``translations``
table: ``org_translations`` and ``site_group_translations`` let an
operator define common banner strings once for an organisation or a
site group instead of re-entering them for every site. Resolution
merges these key-by-key (see ``src.services.translation_resolver``),
unlike the whole-field-replace cascade used for the other config
tables, so this is purely additive — no existing data changes shape.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "org_translations",
        sa.Column("organisation_id", sa.UUID(), nullable=False),
        sa.Column("locale", sa.String(length=10), nullable=False),
        sa.Column("strings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organisation_id", "locale", name="uq_org_translations_org_locale"),
    )
    op.create_index(
        op.f("ix_org_translations_organisation_id"),
        "org_translations",
        ["organisation_id"],
        unique=False,
    )

    op.create_table(
        "site_group_translations",
        sa.Column("site_group_id", sa.UUID(), nullable=False),
        sa.Column("locale", sa.String(length=10), nullable=False),
        sa.Column("strings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["site_group_id"], ["site_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "site_group_id", "locale", name="uq_site_group_translations_group_locale"
        ),
    )
    op.create_index(
        op.f("ix_site_group_translations_site_group_id"),
        "site_group_translations",
        ["site_group_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_site_group_translations_site_group_id"), table_name="site_group_translations"
    )
    op.drop_table("site_group_translations")
    op.drop_index(op.f("ix_org_translations_organisation_id"), table_name="org_translations")
    op.drop_table("org_translations")
