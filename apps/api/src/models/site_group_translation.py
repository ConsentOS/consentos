import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SiteGroupTranslation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Internationalisation strings per site group per locale.

    Sits between ``OrgTranslation`` and ``Translation`` in the cascade:
      Org Translations -> Site Group Translations -> Site Translations
    """

    __tablename__ = "site_group_translations"
    __table_args__ = (
        UniqueConstraint(
            "site_group_id", "locale", name="uq_site_group_translations_group_locale"
        ),
    )

    site_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("site_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    locale: Mapped[str] = mapped_column(String(10), nullable=False)
    strings: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Relationships
    site_group: Mapped["SiteGroup"] = relationship(  # noqa: F821
        back_populates="site_group_translations"
    )
