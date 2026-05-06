"""IAB Global Vendor List (GVL) — local cache of the canonical IAB list.

The GVL is fetched daily from ``vendor-list.consensu.org/v3/vendor-list.json``
by ``src.tasks.iab_gvl.refresh_gvl`` and persisted into these tables so
that the admin UI can present vendor pickers and the API can answer
vendor-metadata queries without re-hitting IAB on every request.

A single ``iab_gvl_meta`` row tracks which GVL version we have. The
other tables are wholly replaced/upserted on each refresh — IAB IDs are
stable across versions so we treat them as the natural primary key.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class IabGvlMeta(TimestampMixin, Base):
    """Singleton row tracking the currently-cached GVL version."""

    __tablename__ = "iab_gvl_meta"

    # Always 1 — the table holds at most one row.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    gvl_specification_version: Mapped[int] = mapped_column(Integer, nullable=False)
    vendor_list_version: Mapped[int] = mapped_column(Integer, nullable=False)
    tcf_policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IabPurpose(TimestampMixin, Base):
    """An IAB consent purpose (1-11 plus future additions)."""

    __tablename__ = "iab_purposes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    illustrations: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)


class IabSpecialPurpose(TimestampMixin, Base):
    """A special purpose (legitimate-interest only, no consent flow)."""

    __tablename__ = "iab_special_purposes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    illustrations: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)


class IabFeature(TimestampMixin, Base):
    """A vendor feature (e.g. matching data to offline sources)."""

    __tablename__ = "iab_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    illustrations: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)


class IabSpecialFeature(TimestampMixin, Base):
    """A special feature (requires explicit user opt-in, e.g. precise geo)."""

    __tablename__ = "iab_special_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    illustrations: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)


class IabDataCategory(TimestampMixin, Base):
    """A data category (introduced in TCF v2.2 GVL v3)."""

    __tablename__ = "iab_data_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class IabVendor(TimestampMixin, Base):
    """An IAB-registered vendor with its declared purposes/features.

    The list-shaped fields (``purposes``, ``features``, etc.) are stored
    as JSONB lists of integer IDs that key into the corresponding
    purpose/feature tables. Storing them denormalised matches how the
    admin UI consumes them and how vendor banners filter by purpose.
    """

    __tablename__ = "iab_vendors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    purposes: Mapped[list[int] | None] = mapped_column(JSONB, nullable=True)
    leg_int_purposes: Mapped[list[int] | None] = mapped_column(JSONB, nullable=True)
    flexible_purposes: Mapped[list[int] | None] = mapped_column(JSONB, nullable=True)
    special_purposes: Mapped[list[int] | None] = mapped_column(JSONB, nullable=True)
    features: Mapped[list[int] | None] = mapped_column(JSONB, nullable=True)
    special_features: Mapped[list[int] | None] = mapped_column(JSONB, nullable=True)
    policy_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uses_cookies: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cookie_refresh: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    uses_non_cookie_access: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # BigInteger — real GVL data has vendors with values exceeding 2^31
    # (effectively "forever" cookies), e.g. 63072000000.
    cookie_max_age_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    data_retention: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    urls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    data_declaration: Mapped[list[int] | None] = mapped_column(JSONB, nullable=True)
