import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class InstallationCheckItem(BaseModel):
    key: str
    label: str
    status: Literal["passed", "failed", "skipped"]
    severity: Literal["error", "warning"]
    detail: str | None = None
    fix: str | None = Field(default=None, description="How to put it right, when it failed.")


class InstallationCheckResult(BaseModel):
    url: str
    checked_at: datetime
    ok: bool = Field(description="True when no check failed, apart from warnings.")
    checks: list[InstallationCheckItem]


class InstallationResponse(BaseModel):
    state: Literal["not_detected", "installed", "problem"]
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_seen_url: str | None = None
    last_check_at: datetime | None = None
    last_check: InstallationCheckResult | None = None


class InstallationSummary(BaseModel):
    site_id: uuid.UUID
    state: Literal["not_detected", "installed", "problem"]
    last_seen_at: datetime | None = None


class CheckInstallationRequest(BaseModel):
    url: str | None = Field(
        default=None,
        description="The page to check. Defaults to the site's home page.",
        max_length=2048,
    )
