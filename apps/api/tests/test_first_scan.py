"""A new site's first scan, and scan progress from the scanner's stream."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.tasks.scanner import ScannerReportedError, stream_scan

try:
    from tests.conftest import create_test_site, requires_db
except ImportError:
    from conftest import create_test_site, requires_db


async def _scans(client, headers, site_id: str) -> list[dict]:
    resp = await client.get(f"/api/v1/scanner/scans/site/{site_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


@requires_db
class TestFirstScanOnCreate:
    async def test_creating_a_site_starts_its_first_scan(self, db_client, auth_headers):
        with patch("src.tasks.scanner.run_scan.delay") as delay:
            site_id = await create_test_site(db_client, auth_headers, domain_prefix="first-scan")

        [job] = await _scans(db_client, auth_headers, site_id)
        assert job["trigger"] == "initial"
        assert job["status"] == "pending"
        assert job["pages_total"] == 50
        delay.assert_called_once_with(job["id"], site_id, 50)

    async def test_first_scan_can_be_skipped(self, db_client, auth_headers):
        with patch("src.tasks.scanner.run_scan.delay") as delay:
            site_id = await create_test_site(
                db_client, auth_headers, domain_prefix="no-first-scan", start_scan=False
            )

        assert await _scans(db_client, auth_headers, site_id) == []
        delay.assert_not_called()

    async def test_site_is_created_when_the_scan_cannot_start(self, db_client, auth_headers):
        with patch("src.tasks.scanner.run_scan.delay", side_effect=ConnectionError):
            site_id = await create_test_site(db_client, auth_headers, domain_prefix="scan-down")

        site = await db_client.get(f"/api/v1/sites/{site_id}", headers=auth_headers)
        assert site.status_code == 200

        [job] = await _scans(db_client, auth_headers, site_id)
        assert job["status"] == "failed"
        assert job["error_message"] == "The scanner couldn't be started"

    async def test_failed_first_scan_can_be_retried(self, db_client, auth_headers):
        with patch("src.tasks.scanner.run_scan.delay", side_effect=ConnectionError):
            site_id = await create_test_site(db_client, auth_headers, domain_prefix="scan-retry")

        with patch("src.tasks.scanner.run_scan.delay"):
            resp = await db_client.post(
                "/api/v1/scanner/scans", json={"site_id": site_id}, headers=auth_headers
            )
        assert resp.status_code == 201
        assert resp.json()["trigger"] == "manual"


@requires_db
class TestStartScan:
    async def _site(self, session, org_id):
        from src.models.site import Site
        from src.models.site_config import SiteConfig

        site = Site(
            id=uuid.uuid4(),
            organisation_id=org_id,
            domain=f"start-{uuid.uuid4().hex[:8]}.com",
            display_name="Start scan",
        )
        session.add(site)
        await session.flush()
        session.add(SiteConfig(site_id=site.id, scan_max_pages=20))
        await session.flush()
        return site

    async def test_refuses_while_a_scan_is_running(self, _test_engine, test_org):
        from sqlalchemy.ext.asyncio import AsyncSession

        from src.models.scan import ScanJob
        from src.services.scanner import ScanInProgressError, start_scan

        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            site = await self._site(session, test_org.id)
            session.add(ScanJob(site_id=site.id, status="running", started_at=datetime.now(UTC)))
            await session.commit()

            with (
                patch("src.tasks.scanner.run_scan.delay") as delay,
                pytest.raises(ScanInProgressError),
            ):
                await start_scan(session, site_id=site.id, trigger="scheduled", max_pages=20)
            delay.assert_not_called()

    async def test_supersedes_a_stale_scan(self, _test_engine, test_org):
        from sqlalchemy.ext.asyncio import AsyncSession

        from src.models.scan import ScanJob
        from src.services.scanner import start_scan

        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            site = await self._site(session, test_org.id)
            stale = ScanJob(
                site_id=site.id,
                status="running",
                started_at=datetime.now(UTC) - timedelta(minutes=30),
                updated_at=datetime.now(UTC) - timedelta(minutes=11),
            )
            session.add(stale)
            await session.commit()

            with patch("src.tasks.scanner.run_scan.delay"):
                job = await start_scan(session, site_id=site.id, trigger="scheduled", max_pages=20)

            await session.refresh(stale)
            assert stale.status == "failed"
            assert job.status == "pending"

    async def test_a_long_scan_that_is_still_progressing_is_not_stale(self, _test_engine, test_org):
        from sqlalchemy.ext.asyncio import AsyncSession

        from src.models.scan import ScanJob
        from src.services.scanner import ScanInProgressError, start_scan

        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            site = await self._site(session, test_org.id)
            session.add(
                ScanJob(
                    site_id=site.id,
                    status="running",
                    started_at=datetime.now(UTC) - timedelta(minutes=30),
                    updated_at=datetime.now(UTC) - timedelta(minutes=1),
                )
            )
            await session.commit()

            with pytest.raises(ScanInProgressError):
                await start_scan(session, site_id=site.id, trigger="manual", max_pages=20)

    async def test_configured_max_pages_reads_the_site_config(self, _test_engine, test_org):
        from sqlalchemy.ext.asyncio import AsyncSession

        from src.services.scanner import configured_max_pages

        async with AsyncSession(_test_engine, expire_on_commit=False) as session:
            site = await self._site(session, test_org.id)
            assert await configured_max_pages(session, site.id) == 20


# ── Reading the scanner's progress stream ────────────────────────────


def _client(lines: list[dict | str], status_code: int = 200) -> httpx.AsyncClient:
    body = "".join((line if isinstance(line, str) else json.dumps(line)) + "\n" for line in lines)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/scan/stream"
        return httpx.Response(status_code, text=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _progress(crawled: int, total: int, cookies: int) -> dict:
    return {
        "type": "progress",
        "pages_crawled": crawled,
        "pages_total": total,
        "cookies_found": cookies,
    }


class TestStreamScan:
    async def test_reports_each_progress_line_and_returns_the_result(self):
        result = {"type": "result", "pages_crawled": 2, "cookies": []}
        seen: list[dict] = []

        async def on_progress(event):
            seen.append(event)

        async with _client([_progress(1, 2, 3), "", _progress(2, 2, 4), result]) as client:
            data = await stream_scan(client, "http://scanner/scan/stream", {}, on_progress)

        assert data == result
        assert [e["pages_crawled"] for e in seen] == [1, 2]

    async def test_an_error_line_raises(self):
        async def on_progress(event):
            pass

        async with _client([{"type": "error", "detail": "browser crashed"}]) as client:
            with pytest.raises(ScannerReportedError, match="browser crashed"):
                await stream_scan(client, "http://scanner/scan/stream", {}, on_progress)

    async def test_a_stream_that_ends_early_is_retryable(self):
        async def on_progress(event):
            pass

        async with _client([_progress(1, 5, 0)]) as client:
            with pytest.raises(httpx.HTTPError):
                await stream_scan(client, "http://scanner/scan/stream", {}, on_progress)

    async def test_http_errors_raise(self):
        async def on_progress(event):
            pass

        async with _client([], status_code=400) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await stream_scan(client, "http://scanner/scan/stream", {}, on_progress)


def test_apply_scan_progress_copies_counts_onto_the_job():
    from src.services.scanner import apply_scan_progress

    job = MagicMock(pages_scanned=0, pages_total=50, cookies_found=0)
    apply_scan_progress(job, _progress(3, 12, 7))

    assert (job.pages_scanned, job.pages_total, job.cookies_found) == (3, 12, 7)


def test_a_retry_keeps_the_requested_page_limit():
    from src.services.scanner import apply_scan_progress
    from src.tasks.scanner import scan_page_limit

    job = MagicMock(pages_scanned=0, pages_total=200, cookies_found=0)
    apply_scan_progress(job, _progress(5, 12, 3))

    assert scan_page_limit(200, job) == 200


def test_a_task_queued_without_a_limit_falls_back_to_the_job():
    from src.tasks.scanner import scan_page_limit

    assert scan_page_limit(None, MagicMock(pages_total=30)) == 30
    assert scan_page_limit(None, MagicMock(pages_total=None)) == 50
