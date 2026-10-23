import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Site(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A domain being managed for cookie consent, belongs to an organisation."""

    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("organisation_id", "domain", name="uq_sites_org_domain"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    additional_domains: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(255)), nullable=True, server_default=None
    )
    site_group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("site_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # The revision the banner serves. ``None`` until the site's first
    # publish, when the banner falls back to its built-in defaults.
    live_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "site_config_revisions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_sites_live_revision_id",
        ),
        nullable=True,
    )
    # Setup checklist: when the owner confirmed or edited the banner, the
    # one step that can't be worked out from the site's data, and when
    # they dismissed the finished checklist.
    banner_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    setup_dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    organisation: Mapped["Organisation"] = relationship(back_populates="sites")  # noqa: F821
    site_group: Mapped["SiteGroup | None"] = relationship(back_populates="sites")  # noqa: F821
    config: Mapped["SiteConfig | None"] = relationship(  # noqa: F821
        back_populates="site", uselist=False
    )
    cookies: Mapped[list["Cookie"]] = relationship(back_populates="site")  # noqa: F821
    cookie_allow_list: Mapped[list["CookieAllowListEntry"]] = relationship(  # noqa: F821
        back_populates="site"
    )
    scan_jobs: Mapped[list["ScanJob"]] = relationship(back_populates="site")  # noqa: F821
    translations: Mapped[list["Translation"]] = relationship(  # noqa: F821
        back_populates="site"
    )
