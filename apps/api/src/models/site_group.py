import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class SiteGroup(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A logical grouping of sites within an organisation (e.g. a brand)."""

    __tablename__ = "site_groups"
    __table_args__ = (UniqueConstraint("organisation_id", "name", name="uq_site_groups_org_name"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    organisation: Mapped["Organisation"] = relationship(  # noqa: F821
        back_populates="site_groups"
    )
    sites: Mapped[list["Site"]] = relationship(back_populates="site_group")  # noqa: F821
    group_config: Mapped["SiteGroupConfig | None"] = relationship(  # noqa: F821
        back_populates="site_group", uselist=False
    )
    site_group_translations: Mapped[list["SiteGroupTranslation"]] = relationship(  # noqa: F821
        back_populates="site_group"
    )
