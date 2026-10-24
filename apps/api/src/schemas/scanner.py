"""Pydantic schemas for scanner and client-side cookie reports."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ScanStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ScanTrigger(StrEnum):
    MANUAL = "manual"
    INITIAL = "initial"
    SCHEDULED = "scheduled"
    CLIENT_REPORT = "client_report"


# ── Client-side cookie report ────────────────────────────────────────


class ReportedCookie(BaseModel):
    """A single cookie/storage item reported by the client-side reporter."""

    name: str = Field(..., min_length=1, max_length=255)
    domain: str = Field(..., min_length=1, max_length=255)
    storage_type: str = Field(default="cookie", max_length=30)
    value_length: int = Field(default=0, ge=0)
    path: str | None = None
    is_secure: bool | None = None
    same_site: str | None = None
    script_source: str | None = None


class CookieReportRequest(BaseModel):
    """Payload from the client-side cookie reporter."""

    site_id: uuid.UUID
    page_url: str = Field(..., max_length=2000)
    cookies: list[ReportedCookie] = Field(..., max_length=500)
    collected_at: datetime
    user_agent: str = Field(default="", max_length=500)


class CookieReportResponse(BaseModel):
    """Acknowledgement response for a cookie report."""

    accepted: bool = True
    cookies_received: int
    new_cookies: int = 0


# ── Scan job schemas ─────────────────────────────────────────────────


class ScanResultResponse(BaseModel):
    """A single scan result — a cookie found on a specific page."""

    id: uuid.UUID
    scan_job_id: uuid.UUID
    page_url: str
    cookie_name: str
    cookie_domain: str
    storage_type: str
    attributes: dict | None = None
    script_source: str | None = None
    auto_category: str | None = None
    initiator_chain: list[str] | None = None
    found_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class ScanJobResponse(BaseModel):
    """Response schema for a scan job."""

    id: uuid.UUID
    site_id: uuid.UUID
    status: str
    trigger: str
    pages_scanned: int
    pages_total: int | None
    cookies_found: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScanJobDetailResponse(ScanJobResponse):
    """Scan job with results included."""

    results: list[ScanResultResponse] = []


class TriggerScanRequest(BaseModel):
    """Request to trigger a new scan."""

    site_id: uuid.UUID
    max_pages: int = Field(default=50, ge=1, le=500)


# ── Diff engine schemas ──────────────────────────────────────────────


class DiffStatus(StrEnum):
    NEW = "new"
    REMOVED = "removed"
    CHANGED = "changed"


class CookieDiffItem(BaseModel):
    """A single cookie difference between two scans."""

    name: str
    domain: str
    storage_type: str
    diff_status: DiffStatus
    details: str | None = None


class ScanDiffResponse(BaseModel):
    """Diff between two scans."""

    current_scan_id: uuid.UUID
    previous_scan_id: uuid.UUID | None
    new_cookies: list[CookieDiffItem] = []
    removed_cookies: list[CookieDiffItem] = []
    changed_cookies: list[CookieDiffItem] = []
    total_new: int = 0
    total_removed: int = 0
    total_changed: int = 0
