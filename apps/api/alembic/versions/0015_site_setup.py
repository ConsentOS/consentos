"""add site setup checklist state

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-18

Two timestamps for the setup checklist: when the banner was confirmed or
edited, and when the finished checklist was dismissed. Every other step
is worked out from the site's data.

Sites that already had a published configuration before this upgrade
are set up already, so both are filled in for them and they never show
the checklist.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


MARK_PUBLISHED_SITES_SET_UP = (
    "UPDATE sites SET banner_confirmed_at = now(), setup_dismissed_at = now() "
    "WHERE live_revision_id IS NOT NULL"
)


def upgrade() -> None:
    op.add_column("sites", sa.Column("banner_confirmed_at", sa.DateTime(timezone=True)))
    op.add_column("sites", sa.Column("setup_dismissed_at", sa.DateTime(timezone=True)))
    op.execute(MARK_PUBLISHED_SITES_SET_UP)


def downgrade() -> None:
    op.drop_column("sites", "setup_dismissed_at")
    op.drop_column("sites", "banner_confirmed_at")
