import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class BlockingMode(StrEnum):
    OPT_IN = "opt_in"
    OPT_OUT = "opt_out"
    INFORMATIONAL = "informational"


# ── Site schemas ─────────────────────────────────────────────────────


class SiteCreate(BaseModel):
    domain: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    additional_domains: list[str] | None = None
    site_group_id: uuid.UUID | None = None


class SiteUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None
    additional_domains: list[str] | None = None
    site_group_id: uuid.UUID | None = None


class SiteResponse(BaseModel):
    id: uuid.UUID
    organisation_id: uuid.UUID
    domain: str
    display_name: str
    is_active: bool
    additional_domains: list[str] | None = None
    site_group_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Site config schemas ──────────────────────────────────────────────


class SiteConfigCreate(BaseModel):
    blocking_mode: BlockingMode = BlockingMode.OPT_IN
    regional_modes: dict | None = None
    tcf_enabled: bool = False
    tcf_publisher_cc: str | None = Field(default=None, max_length=2)
    gpp_enabled: bool = True
    gpp_supported_apis: list[str] | None = None
    gpc_enabled: bool = True
    gpc_jurisdictions: list[str] | None = None
    gpc_global_honour: bool = False
    gcm_enabled: bool = True
    gcm_default: dict | None = None
    shopify_privacy_enabled: bool = False
    banner_config: dict | None = None
    privacy_policy_url: str | None = None
    terms_url: str | None = None
    scan_schedule_cron: str | None = None
    scan_max_pages: int = Field(default=50, ge=1, le=1000)
    consent_expiry_days: int = Field(default=365, ge=1, le=730)
    consent_retention_days: int | None = Field(default=None, ge=1, le=730)
    # None = inherit from the cascade (group → org → system). An
    # explicit list overrides; the resolver re-adds ``necessary``
    # if omitted and drops any unknown slugs.
    enabled_categories: list[str] | None = None


class SiteConfigUpdate(BaseModel):
    blocking_mode: BlockingMode | None = None
    regional_modes: dict | None = None
    tcf_enabled: bool | None = None
    tcf_publisher_cc: str | None = Field(default=None, max_length=2)
    gpp_enabled: bool | None = None
    gpp_supported_apis: list[str] | None = None
    gpc_enabled: bool | None = None
    gpc_jurisdictions: list[str] | None = None
    gpc_global_honour: bool | None = None
    gcm_enabled: bool | None = None
    gcm_default: dict | None = None
    shopify_privacy_enabled: bool | None = None
    banner_config: dict | None = None
    privacy_policy_url: str | None = None
    terms_url: str | None = None
    scan_schedule_cron: str | None = None
    scan_max_pages: int | None = Field(default=None, ge=1, le=1000)
    consent_expiry_days: int | None = Field(default=None, ge=1, le=730)
    consent_retention_days: int | None = Field(default=None, ge=1, le=730)
    enabled_categories: list[str] | None = None


class SiteConfigResponse(BaseModel):
    id: uuid.UUID
    site_id: uuid.UUID
    blocking_mode: str
    regional_modes: dict | None
    tcf_enabled: bool
    tcf_publisher_cc: str | None = None
    gpp_enabled: bool = True
    gpp_supported_apis: list[str] | None = None
    gpc_enabled: bool = True
    gpc_jurisdictions: list[str] | None = None
    gpc_global_honour: bool = False
    gcm_enabled: bool
    gcm_default: dict | None = None
    shopify_privacy_enabled: bool = False
    banner_config: dict | None = None
    privacy_policy_url: str | None = None
    terms_url: str | None = None
    scan_schedule_cron: str | None = None
    scan_max_pages: int = 50
    consent_expiry_days: int = 365
    consent_retention_days: int | None = None
    enabled_categories: list[str] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
