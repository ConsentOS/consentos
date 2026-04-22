import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SiteGroupConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Site-group-level default configuration.

    These defaults sit between org defaults and site config in the cascade:
      System Defaults -> Org Config -> Site Group Config -> Site Config -> Regional Overrides
    """

    __tablename__ = "site_group_configs"

    site_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("site_groups.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # Blocking mode
    blocking_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    regional_modes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # TCF
    tcf_enabled: Mapped[bool | None] = mapped_column(nullable=True)
    tcf_publisher_cc: Mapped[str | None] = mapped_column(String(2), nullable=True)

    # GPP (Global Privacy Platform)
    gpp_enabled: Mapped[bool | None] = mapped_column(nullable=True)
    gpp_supported_apis: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # GPC (Global Privacy Control)
    gpc_enabled: Mapped[bool | None] = mapped_column(nullable=True)
    gpc_jurisdictions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    gpc_global_honour: Mapped[bool | None] = mapped_column(nullable=True)

    # Google Consent Mode
    gcm_enabled: Mapped[bool | None] = mapped_column(nullable=True)
    gcm_default: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Shopify Customer Privacy API
    shopify_privacy_enabled: Mapped[bool | None] = mapped_column(nullable=True)

    # Banner
    banner_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    privacy_policy_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cookie categories shown in the banner. NULL = inherit (system
    # default is all five). See ``SiteConfig.enabled_categories`` for
    # the full cascade semantics.
    enabled_categories: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Scanning
    scan_schedule_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scan_max_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Consent
    consent_expiry_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Cross-domain consent sharing. When enabled, the banner embeds a
    # hidden iframe on the bridge domain to share visitor consent state
    # across different domains in the group.
    consent_sharing_enabled: Mapped[bool | None] = mapped_column(nullable=True)

    # The URL all sites in the group embed the bridge iframe from.
    # Must be a single shared origin so the bridge cookie is the same
    # across all sites (e.g. ``https://cmp.consentos.dev``).
    consent_bridge_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationship
    site_group: Mapped["SiteGroup"] = relationship(back_populates="group_config")  # noqa: F821
