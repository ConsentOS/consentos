"""Read-only response schemas for the IAB GVL endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class GvlMetaResponse(BaseModel):
    """Currently-cached GVL version metadata."""

    model_config = ConfigDict(from_attributes=True)

    gvl_specification_version: int
    vendor_list_version: int
    tcf_policy_version: int
    last_updated: datetime
    synced_at: datetime


class IabVendorResponse(BaseModel):
    """A single IAB-registered vendor."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    purposes: list[int] | None = None
    leg_int_purposes: list[int] | None = None
    flexible_purposes: list[int] | None = None
    special_purposes: list[int] | None = None
    features: list[int] | None = None
    special_features: list[int] | None = None
    policy_url: str | None = None
    deleted_date: datetime | None = None
    uses_cookies: bool | None = None
    cookie_refresh: bool | None = None
    uses_non_cookie_access: bool | None = None
    cookie_max_age_seconds: int | None = None
    data_retention: dict[str, Any] | None = None
    urls: list[dict[str, Any]] | None = None
    data_declaration: list[int] | None = None


class IabVendorListResponse(BaseModel):
    """Paginated list of vendors."""

    items: list[IabVendorResponse]
    total: int
    limit: int
    offset: int
