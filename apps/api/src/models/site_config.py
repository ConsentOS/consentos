import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SiteConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Full configuration for a site: blocking mode, TCF, GCM, banner, scanning, consent."""

    __tablename__ = "site_configs"

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # Blocking mode
    blocking_mode: Mapped[str] = mapped_column(String(20), server_default="opt_in", nullable=False)
    regional_modes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # TCF
    tcf_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    tcf_publisher_cc: Mapped[str | None] = mapped_column(String(2), nullable=True)

    # GPP (Global Privacy Platform)
    gpp_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    gpp_supported_apis: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # GPC (Global Privacy Control)
    gpc_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    gpc_jurisdictions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    gpc_global_honour: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Google Consent Mode
    gcm_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    gcm_default: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Shopify Customer Privacy API
    shopify_privacy_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Banner
    banner_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    display_mode: Mapped[str] = mapped_column(
        String(30), server_default="bottom_banner", nullable=False
    )
    privacy_policy_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cookie categories shown in the banner. When NULL, inherit from the
    # cascade (site-group → org → system default of all five). An explicit
    # list overrides. ``necessary`` is always implicit and will be forced
    # back into the merged result by the resolver, so operators can't
    # accidentally drop it.
    enabled_categories: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # IAB vendor IDs disclosed to the user in the CMP UI (TCF v2.3
    # DisclosedVendors segment). When NULL, inherits from the cascade
    # (site-group → org → system default of an empty list).
    disclosed_vendor_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Scanning
    scan_schedule_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scan_max_pages: Mapped[int] = mapped_column(Integer, server_default="50", nullable=False)

    # Consent
    consent_expiry_days: Mapped[int] = mapped_column(Integer, server_default="365", nullable=False)
    consent_retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationship
    site: Mapped["Site"] = relationship(back_populates="config")  # noqa: F821
