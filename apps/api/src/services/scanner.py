"""Scan orchestration and diff engine.

Provides scan job lifecycle management, result diffing between scans,
and cookie inventory synchronisation from scan results.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.cookie import Cookie, CookieCategory
from src.models.scan import ScanJob, ScanResult
from src.models.site import Site
from src.schemas.scanner import (
    CookieDiffItem,
    DiffStatus,
    ScanDiffResponse,
)


async def create_scan_job(
    db: AsyncSession,
    *,
    site_id: uuid.UUID,
    trigger: str = "manual",
    max_pages: int = 50,
) -> ScanJob:
    """Create a new scan job in 'pending' state."""
    job = ScanJob(
        site_id=site_id,
        status="pending",
        trigger=trigger,
        pages_total=max_pages,
    )
    db.add(job)
    await db.flush()
    return job


async def start_scan_job(db: AsyncSession, job: ScanJob) -> ScanJob:
    """Transition a scan job to 'running'.

    Idempotent: if the job is already running (e.g. Celery re-delivered the
    task after a worker crash), this is a no-op. Also handles re-delivery
    after a transient failure that left the job in 'failed' state mid-retry.
    """
    if job.status == "running":
        return job
    job.status = "running"
    job.started_at = datetime.now(UTC)
    # Reset any previous error so the retry starts clean
    job.error_message = None
    await db.flush()
    return job


async def complete_scan_job(
    db: AsyncSession,
    job: ScanJob,
    *,
    pages_scanned: int = 0,
    cookies_found: int = 0,
    error_message: str | None = None,
) -> ScanJob:
    """Mark a scan job as completed or failed."""
    job.status = "failed" if error_message else "completed"
    job.completed_at = datetime.now(UTC)
    job.pages_scanned = pages_scanned
    job.cookies_found = cookies_found
    job.error_message = error_message
    await db.flush()
    return job


async def add_scan_result(
    db: AsyncSession,
    *,
    scan_job_id: uuid.UUID,
    page_url: str,
    cookie_name: str,
    cookie_domain: str,
    storage_type: str = "cookie",
    attributes: dict | None = None,
    script_source: str | None = None,
    auto_category: str | None = None,
    initiator_chain: list[str] | None = None,
) -> ScanResult:
    """Record a single cookie discovery from a scan."""
    result = ScanResult(
        scan_job_id=scan_job_id,
        page_url=page_url,
        cookie_name=cookie_name,
        cookie_domain=cookie_domain,
        storage_type=storage_type,
        attributes=attributes,
        script_source=script_source,
        auto_category=auto_category,
        initiator_chain=initiator_chain,
    )
    db.add(result)
    await db.flush()
    return result


async def get_previous_completed_scan(
    db: AsyncSession,
    *,
    site_id: uuid.UUID,
    before_scan_id: uuid.UUID,
) -> ScanJob | None:
    """Find the most recent completed scan before the given one."""
    # First get the creation time of the reference scan
    ref_result = await db.execute(select(ScanJob.created_at).where(ScanJob.id == before_scan_id))
    ref_time = ref_result.scalar_one_or_none()
    if ref_time is None:
        return None

    result = await db.execute(
        select(ScanJob)
        .where(
            ScanJob.site_id == site_id,
            ScanJob.status == "completed",
            ScanJob.id != before_scan_id,
            ScanJob.created_at < ref_time,
        )
        .order_by(ScanJob.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _result_key(r: ScanResult) -> tuple[str, str, str]:
    """Unique key for a scan result (cookie identity)."""
    return (r.cookie_name, r.cookie_domain, r.storage_type)


async def compute_scan_diff(
    db: AsyncSession,
    *,
    current_scan_id: uuid.UUID,
    site_id: uuid.UUID,
) -> ScanDiffResponse:
    """Compute the diff between the current scan and the previous one.

    Returns new, removed, and changed cookies. If no previous scan exists,
    all cookies in the current scan are marked as 'new'.
    """
    previous_scan = await get_previous_completed_scan(
        db, site_id=site_id, before_scan_id=current_scan_id
    )

    # Load current scan results
    current_results = await db.execute(
        select(ScanResult).where(ScanResult.scan_job_id == current_scan_id)
    )
    current_items = list(current_results.scalars().all())
    current_keys = {_result_key(r): r for r in current_items}

    if previous_scan is None:
        # No previous scan — everything is new
        new_cookies = [
            CookieDiffItem(
                name=r.cookie_name,
                domain=r.cookie_domain,
                storage_type=r.storage_type,
                diff_status=DiffStatus.NEW,
                details="First scan — no previous data",
            )
            for r in current_items
        ]
        return ScanDiffResponse(
            current_scan_id=current_scan_id,
            previous_scan_id=None,
            new_cookies=new_cookies,
            total_new=len(new_cookies),
        )

    # Load previous scan results
    prev_results = await db.execute(
        select(ScanResult).where(ScanResult.scan_job_id == previous_scan.id)
    )
    prev_items = list(prev_results.scalars().all())
    prev_keys = {_result_key(r): r for r in prev_items}

    new_cookies: list[CookieDiffItem] = []
    removed_cookies: list[CookieDiffItem] = []
    changed_cookies: list[CookieDiffItem] = []

    # New cookies: in current but not in previous
    for key, r in current_keys.items():
        if key not in prev_keys:
            new_cookies.append(
                CookieDiffItem(
                    name=r.cookie_name,
                    domain=r.cookie_domain,
                    storage_type=r.storage_type,
                    diff_status=DiffStatus.NEW,
                )
            )

    # Removed cookies: in previous but not in current
    for key, r in prev_keys.items():
        if key not in current_keys:
            removed_cookies.append(
                CookieDiffItem(
                    name=r.cookie_name,
                    domain=r.cookie_domain,
                    storage_type=r.storage_type,
                    diff_status=DiffStatus.REMOVED,
                )
            )

    # Changed cookies: in both but with different attributes
    for key in current_keys:
        if key in prev_keys:
            curr = current_keys[key]
            prev = prev_keys[key]
            changes: list[str] = []

            if curr.script_source != prev.script_source:
                changes.append("script_source changed")
            if curr.auto_category != prev.auto_category:
                changes.append("auto_category changed")
            # Compare cookie attributes (e.g. secure, httpOnly)
            if (curr.attributes or {}) != (prev.attributes or {}):
                changes.append("attributes changed")

            if changes:
                changed_cookies.append(
                    CookieDiffItem(
                        name=curr.cookie_name,
                        domain=curr.cookie_domain,
                        storage_type=curr.storage_type,
                        diff_status=DiffStatus.CHANGED,
                        details="; ".join(changes),
                    )
                )

    return ScanDiffResponse(
        current_scan_id=current_scan_id,
        previous_scan_id=previous_scan.id,
        new_cookies=new_cookies,
        removed_cookies=removed_cookies,
        changed_cookies=changed_cookies,
        total_new=len(new_cookies),
        total_removed=len(removed_cookies),
        total_changed=len(changed_cookies),
    )


async def sync_scan_results_to_cookies(
    db: AsyncSession,
    *,
    scan_job_id: uuid.UUID,
    site_id: uuid.UUID,
) -> int:
    """Upsert scan results into the site's cookie inventory.

    Creates new Cookie records for newly discovered items or updates
    ``last_seen_at`` for existing ones. When ``auto_category`` is set
    on the scan result and the cookie doesn't already have a
    manually-assigned category, the auto-classified category is
    propagated to the cookie inventory so it shows up categorised in
    the admin UI without requiring manual review.

    Returns the number of new cookies.
    """
    results = await db.execute(select(ScanResult).where(ScanResult.scan_job_id == scan_job_id))
    items = list(results.scalars().all())

    now_iso = datetime.now(UTC).isoformat()
    new_count = 0

    # Pre-load the category slug → id mapping so we don't query per cookie.
    cat_rows = await db.execute(select(CookieCategory))
    slug_to_id: dict[str, uuid.UUID] = {cat.slug: cat.id for cat in cat_rows.scalars().all()}

    for item in items:
        existing = await db.execute(
            select(Cookie).where(
                Cookie.site_id == site_id,
                Cookie.name == item.cookie_name,
                Cookie.domain == item.cookie_domain,
                Cookie.storage_type == item.storage_type,
            )
        )
        cookie = existing.scalar_one_or_none()

        # Resolve the auto-category slug to a category_id.
        auto_cat_id = slug_to_id.get(item.auto_category) if item.auto_category else None

        if cookie:
            cookie.last_seen_at = now_iso
            # Back-fill the category if not manually assigned yet.
            if auto_cat_id and not cookie.category_id:
                cookie.category_id = auto_cat_id
        else:
            cookie = Cookie(
                site_id=site_id,
                name=item.cookie_name,
                domain=item.cookie_domain,
                storage_type=item.storage_type,
                category_id=auto_cat_id,
                review_status="pending",
                first_seen_at=now_iso,
                last_seen_at=now_iso,
            )
            db.add(cookie)
            new_count += 1

    await db.flush()
    return new_count


async def get_sites_due_for_scan(db: AsyncSession) -> list[Site]:
    """Find sites with a scan schedule that are due for scanning.

    A site is due when it has a scan_schedule_cron set and either has
    never been scanned or the last scan completed before the schedule
    interval. For simplicity, this checks the most recent scan's
    completed_at against the current time minus a derived interval.
    """
    from src.models.site_config import SiteConfig

    # Find sites with a cron schedule
    result = await db.execute(
        select(Site)
        .join(SiteConfig, SiteConfig.site_id == Site.id)
        .where(
            Site.deleted_at.is_(None),
            Site.is_active.is_(True),
            SiteConfig.scan_schedule_cron.isnot(None),
        )
    )
    return list(result.scalars().all())
