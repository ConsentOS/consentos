from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Organisation(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Multi-tenant root entity. Each organisation has multiple sites and users."""

    __tablename__ = "organisations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    billing_plan: Mapped[str] = mapped_column(String(50), server_default="free", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    users: Mapped[list["User"]] = relationship(back_populates="organisation")  # noqa: F821
    sites: Mapped[list["Site"]] = relationship(back_populates="organisation")  # noqa: F821
    site_groups: Mapped[list["SiteGroup"]] = relationship(  # noqa: F821
        back_populates="organisation"
    )
    org_config: Mapped["OrgConfig | None"] = relationship(  # noqa: F821
        back_populates="organisation", uselist=False
    )
    org_translations: Mapped[list["OrgTranslation"]] = relationship(  # noqa: F821
        back_populates="organisation"
    )
