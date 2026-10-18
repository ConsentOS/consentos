"""add site_config_revisions

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-18

Immutable published snapshots of each site's config. A trigger rejects
changes to a revision's recorded content. ``sites.live_revision_id``
points at the revision the banner serves.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Kept here rather than imported from the model so this migration stays
# fixed if the model's copy changes later.
REJECT_UPDATE_FUNCTION = """
CREATE OR REPLACE FUNCTION reject_site_config_revision_update() RETURNS trigger AS $$
BEGIN
    IF NEW.site_id IS DISTINCT FROM OLD.site_id
        OR NEW.number IS DISTINCT FROM OLD.number
        OR NEW.consent_version IS DISTINCT FROM OLD.consent_version
        OR NEW.requires_reconsent IS DISTINCT FROM OLD.requires_reconsent
        OR NEW.snapshot IS DISTINCT FROM OLD.snapshot
        OR NEW.site_layer IS DISTINCT FROM OLD.site_layer
        OR NEW.sources IS DISTINCT FROM OLD.sources
        OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
        OR NEW.note IS DISTINCT FROM OLD.note
        OR NEW.published_at IS DISTINCT FROM OLD.published_at
    THEN
        RAISE EXCEPTION 'site_config_revisions rows cannot be changed';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

REJECT_UPDATE_TRIGGER = """
CREATE TRIGGER site_config_revisions_reject_update
    BEFORE UPDATE ON site_config_revisions
    FOR EACH ROW EXECUTE FUNCTION reject_site_config_revision_update()
"""


def upgrade() -> None:
    op.create_table(
        "site_config_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "site_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("consent_version", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requires_reconsent", sa.Boolean(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("site_layer", postgresql.JSONB(), nullable=False),
        sa.Column("sources", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "rolled_back_from_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("site_config_revisions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "published_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("site_id", "number", name="uq_site_config_revisions_site_number"),
        sa.CheckConstraint("number > 0", name="ck_site_config_revisions_number_positive"),
    )
    op.create_index("ix_site_config_revisions_site_id", "site_config_revisions", ["site_id"])
    op.execute(REJECT_UPDATE_FUNCTION)
    op.execute(REJECT_UPDATE_TRIGGER)
    op.add_column(
        "sites",
        sa.Column("live_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_sites_live_revision_id",
        "sites",
        "site_config_revisions",
        ["live_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_sites_live_revision_id", "sites", type_="foreignkey")
    op.drop_column("sites", "live_revision_id")
    op.execute(
        "DROP TRIGGER IF EXISTS site_config_revisions_reject_update ON site_config_revisions"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_site_config_revision_update()")
    op.drop_index("ix_site_config_revisions_site_id", table_name="site_config_revisions")
    op.drop_table("site_config_revisions")
