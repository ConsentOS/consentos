"""Pydantic schemas for cookie categories, cookies, and allow-list entries."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from src.schemas.validators import validate_regex_pattern

# ─── Cookie category schemas ───


class CookieCategoryResponse(BaseModel):
    """Response schema for a cookie category."""

    id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    is_essential: bool
    display_order: int
    tcf_purpose_ids: list[int] | None = None
    gcm_consent_types: list[str] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Storage type enum ───


class StorageType(StrEnum):
    """Type of browser storage used by the cookie/tracker."""

    cookie = "cookie"
    local_storage = "local_storage"
    session_storage = "session_storage"
    indexed_db = "indexed_db"


# ─── Review status enum ───


class ReviewStatus(StrEnum):
    """Review status for a discovered cookie."""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"


# ─── Cookie schemas ───


class CookieCreate(BaseModel):
    """Schema for creating a cookie record (typically from scanner/reporter)."""

    name: str = Field(..., min_length=1, max_length=255)
    domain: str = Field(..., min_length=1, max_length=255)
    storage_type: StorageType = StorageType.cookie
    category_id: uuid.UUID | None = None
    description: str | None = None
    vendor: str | None = Field(None, max_length=255)
    path: str | None = Field(None, max_length=500)
    max_age_seconds: int | None = None
    is_http_only: bool | None = None
    is_secure: bool | None = None
    same_site: str | None = Field(None, max_length=10)


class CookieUpdate(BaseModel):
    """Schema for updating a cookie record."""

    category_id: uuid.UUID | None = None
    description: str | None = None
    vendor: str | None = Field(None, max_length=255)
    review_status: ReviewStatus | None = None


class CookieResponse(BaseModel):
    """Response schema for a cookie."""

    id: uuid.UUID
    site_id: uuid.UUID
    category_id: uuid.UUID | None = None
    name: str
    domain: str
    storage_type: str
    description: str | None = None
    vendor: str | None = None
    path: str | None = None
    max_age_seconds: int | None = None
    is_http_only: bool | None = None
    is_secure: bool | None = None
    same_site: str | None = None
    review_status: str
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Allow-list schemas ───


class AllowListEntryCreate(BaseModel):
    """Schema for adding a cookie to the allow-list."""

    name_pattern: str = Field(..., min_length=1, max_length=255)
    domain_pattern: str = Field(..., min_length=1, max_length=255)
    category_id: uuid.UUID
    description: str | None = None


class AllowListEntryUpdate(BaseModel):
    """Schema for updating an allow-list entry."""

    category_id: uuid.UUID | None = None
    description: str | None = None


class AllowListEntryResponse(BaseModel):
    """Response schema for an allow-list entry."""

    id: uuid.UUID
    site_id: uuid.UUID
    category_id: uuid.UUID
    name_pattern: str
    domain_pattern: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Known cookie schemas ───


class KnownCookieCreate(BaseModel):
    """Schema for creating a known cookie pattern."""

    name_pattern: str = Field(..., min_length=1, max_length=255)
    domain_pattern: str = Field(..., min_length=1, max_length=255)
    category_id: uuid.UUID
    vendor: str | None = Field(None, max_length=255)
    description: str | None = None
    is_regex: bool = False

    @model_validator(mode="after")
    def _validate_regex_patterns(self) -> KnownCookieCreate:
        if self.is_regex:
            validate_regex_pattern(self.name_pattern)
            validate_regex_pattern(self.domain_pattern)
        return self


class KnownCookieUpdate(BaseModel):
    """Schema for updating a known cookie pattern."""

    category_id: uuid.UUID | None = None
    vendor: str | None = Field(None, max_length=255)
    description: str | None = None
    is_regex: bool | None = None


class KnownCookieResponse(BaseModel):
    """Response schema for a known cookie pattern."""

    id: uuid.UUID
    name_pattern: str
    domain_pattern: str
    category_id: uuid.UUID
    vendor: str | None = None
    description: str | None = None
    is_regex: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Classification schemas ───


class ClassificationResultResponse(BaseModel):
    """Response for a single cookie classification result."""

    cookie_name: str
    cookie_domain: str
    category_id: uuid.UUID | None = None
    category_slug: str | None = None
    vendor: str | None = None
    description: str | None = None
    match_source: str
    matched: bool


class ClassifySiteResponse(BaseModel):
    """Response for classifying all cookies on a site."""

    site_id: str
    total: int
    matched: int
    unmatched: int
    results: list[ClassificationResultResponse]


class ClassifySingleRequest(BaseModel):
    """Request to classify a single cookie (preview/test)."""

    cookie_name: str = Field(..., min_length=1, max_length=255)
    cookie_domain: str = Field(..., min_length=1, max_length=255)
