import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class SiteInstallation(TimestampMixin, Base):
    """Whether, and how well, the banner is installed on a site.

    Kept apart from ``sites`` because ``last_seen_at`` is written often,
    whenever the banner loads on one of the site's pages.
    """

    __tablename__ = "site_installations"

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        primary_key=True,
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The page the banner last loaded on, without its query string.
    last_seen_url: Mapped[str | None] = mapped_column(Text)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Findings from the last "Check now", as returned by
    # ``GET /sites/{id}/installation``.
    last_check: Mapped[dict | None] = mapped_column(JSONB)
