import uuid
from datetime import datetime

from sqlalchemy import (
    DDL,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UUIDPrimaryKeyMixin


class SiteConfigRevision(UUIDPrimaryKeyMixin, Base):
    """A published, immutable snapshot of what a site serves.

    ``snapshot`` holds the fully resolved config with every parent layer
    baked in, so serving or rolling back to a revision never depends on
    the current state of the organisation or site group config.

    Rows are never updated. There is no ``updated_at``, and a trigger
    rejects any ``UPDATE`` so the history can be relied on as a record
    of what each site served.
    """

    __tablename__ = "site_config_revisions"
    __table_args__ = (
        UniqueConstraint("site_id", "number", name="uq_site_config_revisions_site_number"),
        CheckConstraint("number > 0", name="ck_site_config_revisions_number_positive"),
    )

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Served to the banner as ``config.id``. Carried over from the
    # previous revision unless the publisher asks visitors to consent
    # again, so ordinary publishes don't re-prompt anyone.
    consent_version: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requires_reconsent: Mapped[bool] = mapped_column(default=False, nullable=False)

    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    site_layer: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sources: Mapped[list] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    rolled_back_from_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("site_config_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


# Shared with migration 0013 so tests built with ``create_all`` get the
# same guarantee as a migrated database. ``ON DELETE SET NULL`` on
# ``rolled_back_from_id`` and ``published_by`` would itself be an
# UPDATE, so only changes to the recorded content are rejected.
REJECT_REVISION_UPDATE_FUNCTION = """
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

REJECT_REVISION_UPDATE_TRIGGER = """
CREATE TRIGGER site_config_revisions_reject_update
    BEFORE UPDATE ON site_config_revisions
    FOR EACH ROW EXECUTE FUNCTION reject_site_config_revision_update()
"""

event.listen(
    SiteConfigRevision.__table__,
    "after_create",
    DDL(REJECT_REVISION_UPDATE_FUNCTION).execute_if(dialect="postgresql"),
)
event.listen(
    SiteConfigRevision.__table__,
    "after_create",
    DDL(REJECT_REVISION_UPDATE_TRIGGER).execute_if(dialect="postgresql"),
)
