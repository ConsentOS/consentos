import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UUIDPrimaryKeyMixin


class ConsentRecord(UUIDPrimaryKeyMixin, Base):
    """Audit trail of every consent event. Partitioned by month for performance."""

    __tablename__ = "consent_records"
    __table_args__ = (
        # Composite index for the most common analytics query pattern:
        # "records for site X between dates A and B". The (site_id,
        # consented_at DESC) ordering also supports "latest consents
        # for site X" without an extra sort.
        Index(
            "ix_consent_records_site_consented_at",
            "site_id",
            "consented_at",
        ),
    )

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Visitor identification (anonymous)
    visitor_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Consent details
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    categories_accepted: Mapped[list] = mapped_column(JSONB, nullable=False)
    categories_rejected: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # TCF
    tc_string: Mapped[str | None] = mapped_column(Text, nullable=True)

    # GCM state at time of consent
    gcm_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # GPP
    gpp_string: Mapped[str | None] = mapped_column(Text, nullable=True)

    # GPC
    gpc_detected: Mapped[bool | None] = mapped_column(nullable=True)
    gpc_honoured: Mapped[bool | None] = mapped_column(nullable=True)

    # Context
    page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(5), nullable=True)
    region_code: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Timestamp
    consented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
