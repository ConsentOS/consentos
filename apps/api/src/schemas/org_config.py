import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from src.schemas.site import BlockingMode


class OrgConfigUpdate(BaseModel):
    """Update (or create) organisation-level default configuration.

    All fields are optional — only non-None values override the system defaults.
    """

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


class OrgConfigResponse(BaseModel):
    id: uuid.UUID
    organisation_id: uuid.UUID
    blocking_mode: str | None
    regional_modes: dict | None
    tcf_enabled: bool | None
    tcf_publisher_cc: str | None
    gpp_enabled: bool | None
    gpp_supported_apis: list[str] | None
    gpc_enabled: bool | None
    gpc_jurisdictions: list[str] | None
    gpc_global_honour: bool | None
    gcm_enabled: bool | None
    gcm_default: dict | None
    shopify_privacy_enabled: bool | None
    banner_config: dict | None
    privacy_policy_url: str | None
    terms_url: str | None
    scan_schedule_cron: str | None
    scan_max_pages: int | None
    consent_expiry_days: int | None
    consent_retention_days: int | None
    enabled_categories: list[str] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
