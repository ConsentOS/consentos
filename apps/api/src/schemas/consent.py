import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ConsentAction(StrEnum):
    ACCEPT_ALL = "accept_all"
    REJECT_ALL = "reject_all"
    CUSTOM = "custom"
    WITHDRAW = "withdraw"


class ConsentRecordCreate(BaseModel):
    """Payload sent by the banner when a consent event occurs."""

    site_id: uuid.UUID
    visitor_id: str = Field(min_length=1, max_length=255)
    action: ConsentAction
    categories_accepted: list[str]
    categories_rejected: list[str] | None = None
    tc_string: str | None = None
    gcm_state: dict | None = None
    gpp_string: str | None = None
    gpc_detected: bool | None = None
    gpc_honoured: bool | None = None
    page_url: str | None = None
    country_code: str | None = Field(default=None, max_length=5)
    region_code: str | None = Field(default=None, max_length=10)
    # The ``revision_id`` of the config the visitor saw. Its consent
    # version is recorded from the revision itself.
    config_revision_id: uuid.UUID | None = None


class ConsentRecordResponse(BaseModel):
    id: uuid.UUID
    site_id: uuid.UUID
    visitor_id: str
    action: str
    categories_accepted: list
    categories_rejected: list | None = None
    tc_string: str | None = None
    gcm_state: dict | None = None
    gpp_string: str | None = None
    gpc_detected: bool | None = None
    gpc_honoured: bool | None = None
    page_url: str | None = None
    country_code: str | None = None
    region_code: str | None = None
    config_revision_id: uuid.UUID | None = None
    consent_version: uuid.UUID | None = None
    # The revision's version number, for display.
    config_revision_number: int | None = None
    consented_at: datetime

    model_config = {"from_attributes": True}


class ConsentRecordListResponse(BaseModel):
    """Paginated list of consent records."""

    items: list[ConsentRecordResponse]
    total: int
    page: int
    page_size: int


class ConsentVerifyResponse(BaseModel):
    """Audit proof that a consent record exists."""

    id: uuid.UUID
    site_id: uuid.UUID
    visitor_id: str
    action: str
    categories_accepted: list
    consented_at: datetime
    valid: bool = True
