"""Celery tasks for scan job execution and scheduling.

The run_scan task calls the scanner HTTP service to execute a Playwright
crawl, then processes the results: stores scan results, runs auto-
classification, syncs discovered cookies to the site inventory, and
computes diffs against the previous scan.
"""

from __future__ import annotations

import logging
import uuid

import httpx

from src.celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="src.tasks.scanner.run_scan", bind=True, max_retries=2)
def run_scan(self, scan_job_id: str, site_id: str) -> dict:
    """Execute a scan job by calling the scanner service.

    1. Transition job to 'running'
    2. Look up site domain
    3. Call scanner HTTP service with the domain
    4. Store scan results and run auto-classification
    5. Sync discovered cookies to the site inventory
    6. Mark job as completed
    """
    import asyncio

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from src.config.settings import get_settings
    from src.models.scan import ScanJob
    from src.models.site import Site
    from src.services.classification import classify_single_cookie
    from src.services.scanner import (
        add_scan_result,
        complete_scan_job,
        start_scan_job,
        sync_scan_results_to_cookies,
    )

    settings = get_settings()
    job_uuid = uuid.UUID(scan_job_id)
    site_uuid = uuid.UUID(site_id)

    async def _execute() -> dict:
        engine = create_async_engine(settings.database_url, echo=False)
        async with AsyncSession(engine, expire_on_commit=False) as db:
            try:
                # Load the job
                result = await db.execute(select(ScanJob).where(ScanJob.id == job_uuid))
                job = result.scalar_one_or_none()
                if job is None:
                    return {"error": "Scan job not found"}

                # Load the site to get the domain
                site_result = await db.execute(select(Site).where(Site.id == site_uuid))
                site = site_result.scalar_one_or_none()
                if site is None:
                    return {"error": "Site not found"}

                # Transition to running
                await start_scan_job(db, job)
                await db.commit()

                # Call the scanner service
                scanner_url = f"{settings.scanner_service_url}/scan"
                max_pages = job.pages_total or 50

                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(settings.scanner_timeout_seconds)
                ) as client:
                    resp = await client.post(
                        scanner_url,
                        json={
                            "domain": site.domain,
                            "max_pages": max_pages,
                        },
                    )
                    resp.raise_for_status()
                    scan_data = resp.json()

                # Store scan results
                cookies = scan_data.get("cookies", [])
                pages_crawled = scan_data.get("pages_crawled", 0)

                for cookie in cookies:
                    # Auto-classify the cookie
                    category = await classify_single_cookie(
                        db,
                        site_id=site_uuid,
                        cookie_name=cookie["name"],
                        cookie_domain=cookie["domain"],
                    )

                    await add_scan_result(
                        db,
                        scan_job_id=job_uuid,
                        page_url=cookie.get("page_url", ""),
                        cookie_name=cookie["name"],
                        cookie_domain=cookie["domain"],
                        storage_type=cookie.get("storage_type", "cookie"),
                        attributes={
                            "path": cookie.get("path"),
                            "http_only": cookie.get("http_only"),
                            "secure": cookie.get("secure"),
                            "same_site": cookie.get("same_site"),
                            "value_length": cookie.get("value_length", 0),
                        },
                        script_source=cookie.get("script_source"),
                        auto_category=category.category_slug if category else None,
                        initiator_chain=cookie.get("initiator_chain") or None,
                    )

                await db.commit()

                # Mark job as completed
                await complete_scan_job(
                    db,
                    job,
                    pages_scanned=pages_crawled,
                    cookies_found=len(cookies),
                )
                await db.commit()

                # Sync results to cookie inventory
                new_cookies = await sync_scan_results_to_cookies(
                    db,
                    scan_job_id=job_uuid,
                    site_id=site_uuid,
                )
                await db.commit()

                logger.info(
                    "Scan %s completed: %d pages, %d cookies, %d new",
                    scan_job_id,
                    pages_crawled,
                    len(cookies),
                    new_cookies,
                )

                return {
                    "scan_job_id": scan_job_id,
                    "status": "completed",
                    "pages_scanned": pages_crawled,
                    "cookies_found": len(cookies),
                    "new_cookies_synced": new_cookies,
                }

            except httpx.HTTPError as exc:
                logger.error("Scanner service error for job %s: %s", scan_job_id, exc)
                await db.rollback()
                # Only mark failed on the final retry; otherwise let the
                # retry set status back to "running" cleanly.
                if self.request.retries >= self.max_retries:
                    await _mark_failed(db, job_uuid, f"Scanner service error: {exc}")
                raise self.retry(exc=exc, countdown=30) from exc

            except Exception as exc:
                logger.exception("Scan task failed for job %s", scan_job_id)
                await db.rollback()
                await _mark_failed(db, job_uuid, str(exc))
                return {"error": str(exc)}

            finally:
                await engine.dispose()

    return asyncio.run(_execute())


async def _mark_failed(db, job_uuid: uuid.UUID, message: str) -> None:
    """Mark a scan job as failed."""
    from sqlalchemy import select

    from src.models.scan import ScanJob
    from src.services.scanner import complete_scan_job

    try:
        result = await db.execute(select(ScanJob).where(ScanJob.id == job_uuid))
        job = result.scalar_one_or_none()
        if job:
            await complete_scan_job(db, job, error_message=message)
            await db.commit()
    except Exception:
        logger.exception("Failed to mark scan job %s as failed", job_uuid)


@app.task(name="src.tasks.scanner.check_scheduled_scans")
def check_scheduled_scans() -> dict:
    """Periodic task: check which sites are due for a scheduled scan.

    Runs every 15 minutes via Celery Beat. ``get_sites_due_for_scan``
    evaluates each site's ``scan_schedule_cron`` against its last scan, so
    a site is only scanned once its cron has actually come due — not on
    every tick. Blank/disabled schedules are ignored.
    """
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from src.config.settings import get_settings
    from src.services.scanner import create_scan_job, get_sites_due_for_scan

    settings = get_settings()

    async def _check() -> dict:
        engine = create_async_engine(settings.database_url, echo=False)
        async with AsyncSession(engine, expire_on_commit=False) as db:
            try:
                sites = await get_sites_due_for_scan(db)
                triggered = 0

                for site in sites:
                    job = await create_scan_job(db, site_id=site.id, trigger="scheduled")
                    await db.commit()
                    # Dispatch the scan task
                    run_scan.delay(str(job.id), str(site.id))
                    triggered += 1

                return {"sites_checked": len(sites), "scans_triggered": triggered}
            except Exception:
                await db.rollback()
                raise
            finally:
                await engine.dispose()

    return asyncio.run(_check())


@app.task(name="src.tasks.scanner.recover_stale_scans")
def recover_stale_scans() -> dict:
    """Periodic task: detect and recover scan jobs stuck in pending/running.

    - Jobs stuck in 'pending' for >5 minutes are re-dispatched to Celery.
    - Jobs stuck in 'running' for >10 minutes are marked as failed.
    """
    import asyncio
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import or_, select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from src.config.settings import get_settings
    from src.models.scan import ScanJob
    from src.services.scanner import complete_scan_job

    settings = get_settings()

    async def _recover() -> dict:
        engine = create_async_engine(settings.database_url, echo=False)
        async with AsyncSession(engine, expire_on_commit=False) as db:
            try:
                now = datetime.now(UTC)
                stale_pending_cutoff = now - timedelta(minutes=5)
                stale_running_cutoff = now - timedelta(minutes=10)

                result = await db.execute(
                    select(ScanJob).where(
                        or_(
                            # Pending too long — likely never picked up
                            (ScanJob.status == "pending")
                            & (ScanJob.created_at < stale_pending_cutoff),
                            # Running too long — likely worker died
                            (ScanJob.status == "running")
                            & (ScanJob.started_at < stale_running_cutoff),
                        )
                    )
                )
                stale_jobs = list(result.scalars().all())

                redispatched = 0
                failed = 0

                for job in stale_jobs:
                    if job.status == "pending":
                        # Re-dispatch to Celery
                        logger.warning("Re-dispatching stale pending scan job %s", job.id)
                        run_scan.delay(str(job.id), str(job.site_id))
                        redispatched += 1
                    elif job.status == "running":
                        # Mark as failed — the worker likely died
                        logger.warning("Failing stale running scan job %s", job.id)
                        await complete_scan_job(
                            db,
                            job,
                            error_message=(
                                "Job timed out (running too long, worker may have crashed)"
                            ),
                        )
                        failed += 1

                await db.commit()
                return {
                    "stale_jobs_found": len(stale_jobs),
                    "redispatched": redispatched,
                    "failed": failed,
                }
            except Exception:
                await db.rollback()
                raise
            finally:
                await engine.dispose()

    return asyncio.run(_recover())
