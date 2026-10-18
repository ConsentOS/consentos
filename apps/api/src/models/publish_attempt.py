import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UUIDPrimaryKeyMixin


class PublishAttempt(UUIDPrimaryKeyMixin, Base):
    """One publish, rollback or bulk-publish item, whether it worked or not.

    Kept so a failure is still visible after the dialog that reported it
    has closed.
    """

    __tablename__ = "publish_attempts"
    __table_args__ = (
        CheckConstraint(
            "action IN ('publish', 'rollback', 'bulk_publish')",
            name="ck_publish_attempts_action",
        ),
        CheckConstraint(
            "status IN ('succeeded', 'failed')",
            name="ck_publish_attempts_status",
        ),
        Index("ix_publish_attempts_site_attempted", "site_id", "attempted_at"),
    )

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("site_config_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Groups the items of one bulk publish.
    batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    attempted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
