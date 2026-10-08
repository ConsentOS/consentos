"""Scanner and client-side cookie report endpoints.

Accepts cookie reports from the client-side reporter embedded in the banner
bundle, upserts discovered cookies into the site's cookie inventory, and
provides scan job management (trigger, list, detail, diff).
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.cookie import Cookie
from src.models.scan import ScanJob, ScanResult
from src.models.site import Site
from src.schemas.auth import CurrentUser
from src.schemas.scanner import (
    CookieReportRequest,
    CookieReportResponse,
    ScanDiffResponse,
    ScanJobDetailResponse,
    ScanJobResponse,
    TriggerScanRequest,
)
from src.services.dependencies import get_current_user
from src.services.scanner import (
    compute_scan_diff,
    create_scan_job,
)
from src.services.site_domains import (
    host_matches_site,
    require_host_on_site,
    require_request_from_site,
    url_host,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scanner", tags=["scanner"])


# ── Client-side cookie report (public, no auth) ─────────────────────


@router.post(
    "/report",
    response_model=CookieReportResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_cookie_report(
    body: CookieReportRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CookieReportResponse:
    """Receive a cookie report from the client-side reporter.

    This is a public endpoint (no auth) since it's called from the banner
    script running on end-user browsers. The site_id acts as implicit auth.

    The site must be active. The report's ``page_url`` and, when usable,
    the request's ``Origin`` or ``Referer`` must belong to the site's
    domains. Reported cookies whose
    domain lies outside the site's domains are ignored.
    """
    # Verify site exists
    site_result = await db.execute(
        select(Site).where(
            Site.id == body.site_id,
            Site.is_active.is_(True),
            Site.deleted_at.is_(None),
        )
    )
    site = site_result.scalar_one_or_none()
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found",
        )

    require_host_on_site(url_host(body.page_url), site, detail="Page URL does not match site")
    require_request_from_site(request, site)

    new_cookies = 0
    now_iso = datetime.now(UTC).isoformat()

    for reported in body.cookies:
        if not host_matches_site(reported.domain, site):
            continue

        # Check if this cookie already exists for the site
        existing = await db.execute(
            select(Cookie).where(
                Cookie.site_id == body.site_id,
                Cookie.name == reported.name,
                Cookie.domain == reported.domain,
                Cookie.storage_type == reported.storage_type,
            )
        )
        cookie = existing.scalar_one_or_none()

        if cookie:
            # Update last_seen_at timestamp
            cookie.last_seen_at = now_iso
        else:
            # Create new cookie record
            cookie = Cookie(
                site_id=body.site_id,
                name=reported.name,
                domain=reported.domain,
                storage_type=reported.storage_type,
                path=reported.path,
                is_secure=reported.is_secure,
                same_site=reported.same_site,
                review_status="pending",
                first_seen_at=now_iso,
                last_seen_at=now_iso,
            )
            db.add(cookie)
            new_cookies += 1

    await db.flush()

    return CookieReportResponse(
        accepted=True,
        cookies_received=len(body.cookies),
        new_cookies=new_cookies,
    )


# ── Scan job management (authenticated) ─────────────────────────────


async def _verify_site_access(
    site_id: uuid.UUID,
    user: CurrentUser,
    db: AsyncSession,
) -> Site:
    """Verify site exists and belongs to the user's organisation."""
    result = await db.execute(
        select(Site).where(
            Site.id == site_id,
            Site.organisation_id == user.organisation_id,
            Site.deleted_at.is_(None),
        )
    )
    site = result.scalar_one_or_none()
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found",
        )
    return site


@router.post(
    "/scans",
    response_model=ScanJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_scan(
    body: TriggerScanRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> ScanJob:
    """Trigger a new cookie scan for a site.

    Creates a scan job in 'pending' state and dispatches it to the
    Celery worker queue for execution.
    """
    from src.services.scanner import complete_scan_job

    await _verify_site_access(body.site_id, user, db)

    # Check for an already-running scan
    active_result = await db.execute(
        select(ScanJob).where(
            ScanJob.site_id == body.site_id,
            ScanJob.status.in_(["pending", "running"]),
        )
    )
    active_jobs = list(active_result.scalars().all())

    now = datetime.now(UTC)
    stale_pending_cutoff = now - timedelta(minutes=5)
    stale_running_cutoff = now - timedelta(minutes=10)

    for active_job in active_jobs:
        is_stale_pending = (
            active_job.status == "pending"
            and active_job.created_at.replace(tzinfo=UTC) < stale_pending_cutoff
        )
        is_stale_running = (
            active_job.status == "running"
            and active_job.started_at
            and active_job.started_at.replace(tzinfo=UTC) < stale_running_cutoff
        )
        if is_stale_pending or is_stale_running:
            logger.warning(
                "Failing stale %s scan job %s for site %s",
                active_job.status,
                active_job.id,
                body.site_id,
            )
            await complete_scan_job(
                db,
                active_job,
                error_message=(
                    f"Job was stale ({active_job.status} too long), superseded by new scan"
                ),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A scan is already in progress for this site",
            )

    job = await create_scan_job(
        db,
        site_id=body.site_id,
        trigger="manual",
        max_pages=body.max_pages,
    )

    # Commit before dispatching to Celery so the worker can find the
    # job in the database immediately (avoids race condition).
    await db.commit()

    # Dispatch to Celery (import here to avoid import at module level
    # when Celery broker is unavailable during testing)
    try:
        from src.tasks.scanner import run_scan

        run_scan.delay(str(job.id), str(body.site_id))
    except Exception:
        logger.exception("Failed to dispatch scan job %s to Celery", job.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Background task queue is unavailable — scan job"
                " created but cannot be processed. Please try again later."
            ),
        ) from None

    return job


@router.get("/scans/site/{site_id}", response_model=list[ScanJobResponse])
async def list_scans(
    site_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[ScanJob]:
    """List scan jobs for a site, most recent first."""
    await _verify_site_access(site_id, user, db)

    result = await db.execute(
        select(ScanJob)
        .where(ScanJob.site_id == site_id)
        .order_by(ScanJob.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


@router.get("/scans/{scan_id}", response_model=ScanJobDetailResponse)
async def get_scan(
    scan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Retrieve a scan job with its results."""
    result = await db.execute(select(ScanJob).where(ScanJob.id == scan_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan job not found",
        )

    # Verify org access
    await _verify_site_access(job.site_id, user, db)

    # Load results
    results = await db.execute(
        select(ScanResult).where(ScanResult.scan_job_id == scan_id).order_by(ScanResult.cookie_name)
    )
    scan_results = list(results.scalars().all())

    return {
        "id": job.id,
        "site_id": job.site_id,
        "status": job.status,
        "trigger": job.trigger,
        "pages_scanned": job.pages_scanned,
        "pages_total": job.pages_total,
        "cookies_found": job.cookies_found,
        "error_message": job.error_message,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "results": scan_results,
    }


@router.get("/scans/{scan_id}/diff", response_model=ScanDiffResponse)
async def get_scan_diff(
    scan_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> ScanDiffResponse:
    """Get the diff between a scan and its predecessor."""
    result = await db.execute(select(ScanJob).where(ScanJob.id == scan_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scan job not found",
        )

    await _verify_site_access(job.site_id, user, db)

    return await compute_scan_diff(db, current_scan_id=scan_id, site_id=job.site_id)
