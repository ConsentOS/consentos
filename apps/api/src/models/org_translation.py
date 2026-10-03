import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OrgTranslation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Internationalisation strings per organisation per locale.

    Sits above ``SiteGroupTranslation``/``Translation`` in the cascade so
    common strings can be defined once for every site in the
    organisation instead of being re-entered per site.
    """

    __tablename__ = "org_translations"
    __table_args__ = (
        UniqueConstraint("organisation_id", "locale", name="uq_org_translations_org_locale"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    locale: Mapped[str] = mapped_column(String(10), nullable=False)
    strings: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Relationships
    organisation: Mapped["Organisation"] = relationship(  # noqa: F821
        back_populates="org_translations"
    )
