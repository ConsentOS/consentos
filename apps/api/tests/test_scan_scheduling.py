"""Tests for scan scheduling, diff engine, and scan endpoints — CMP-24.

Covers:
  - Scanner schemas (new additions)
  - Scan service (job lifecycle, diff engine, cookie sync)
  - Scanner router (trigger, list, detail, diff endpoints)
  - Integration tests against live database
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.schemas.scanner import (
    CookieDiffItem,
    DiffStatus,
    ScanDiffResponse,
    ScanJobDetailResponse,
    ScanResultResponse,
    TriggerScanRequest,
)

# ── Schema tests ─────────────────────────────────────────────────────


class TestSchemas:
    """Validate scanner schema additions."""

    def test_scan_result_response(self):
        r = ScanResultResponse(
            id=uuid.uuid4(),
            scan_job_id=uuid.uuid4(),
            page_url="https://example.com",
            cookie_name="_ga",
            cookie_domain=".example.com",
            storage_type="cookie",
            found_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        assert r.cookie_name == "_ga"

    def test_scan_job_detail_response(self):
        r = ScanJobDetailResponse(
            id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            status="completed",
            trigger="manual",
            pages_scanned=5,
            pages_total=10,
            cookies_found=3,
            error_message=None,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            results=[],
        )
        assert r.status == "completed"
        assert r.results == []

    def test_trigger_scan_request(self):
        req = TriggerScanRequest(site_id=uuid.uuid4(), max_pages=100)
        assert req.max_pages == 100

    def test_trigger_scan_request_defaults(self):
        req = TriggerScanRequest(site_id=uuid.uuid4())
        assert req.max_pages == 50

    def test_trigger_scan_max_pages_validation(self):
        with pytest.raises(ValueError):
            TriggerScanRequest(site_id=uuid.uuid4(), max_pages=0)
        with pytest.raises(ValueError):
            TriggerScanRequest(site_id=uuid.uuid4(), max_pages=501)

    def test_diff_status_values(self):
        assert DiffStatus.NEW == "new"
        assert DiffStatus.REMOVED == "removed"
        assert DiffStatus.CHANGED == "changed"

    def test_cookie_diff_item(self):
        item = CookieDiffItem(
            name="_ga",
            domain=".example.com",
            storage_type="cookie",
            diff_status=DiffStatus.NEW,
            details="First scan",
        )
        assert item.diff_status == "new"

    def test_scan_diff_response(self):
        resp = ScanDiffResponse(
            current_scan_id=uuid.uuid4(),
            previous_scan_id=uuid.uuid4(),
            new_cookies=[
                CookieDiffItem(
                    name="_ga",
                    domain=".example.com",
                    storage_type="cookie",
                    diff_status=DiffStatus.NEW,
                ),
            ],
            total_new=1,
        )
        assert resp.total_new == 1
        assert len(resp.new_cookies) == 1

    def test_scan_diff_response_no_previous(self):
        resp = ScanDiffResponse(
            current_scan_id=uuid.uuid4(),
            previous_scan_id=None,
        )
        assert resp.previous_scan_id is None
        assert resp.total_new == 0


# ── Diff engine unit tests ───────────────────────────────────────────


class TestDiffEngine:
    """Test the scan diff engine with mocked data."""

    def _make_scan_result(
        self,
        name: str = "_ga",
        domain: str = ".example.com",
        storage_type: str = "cookie",
        script_source: str | None = None,
        auto_category: str | None = None,
        attributes: dict | None = None,
    ):
        """Create a mock ScanResult."""
        mock = MagicMock()
        mock.cookie_name = name
        mock.cookie_domain = domain
        mock.storage_type = storage_type
        mock.script_source = script_source
        mock.auto_category = auto_category
        mock.attributes = attributes
        return mock

    def test_result_key(self):
        from src.services.scanner import _result_key

        mock = self._make_scan_result("_ga", ".example.com", "cookie")
        assert _result_key(mock) == ("_ga", ".example.com", "cookie")

    def test_result_key_different_storage(self):
        from src.services.scanner import _result_key

        mock = self._make_scan_result("key", "example.com", "local_storage")
        assert _result_key(mock) == ("key", "example.com", "local_storage")


# ── Scan service unit tests ──────────────────────────────────────────


class TestScanService:
    """Test scan service functions with mocked DB."""

    @pytest.mark.asyncio
    async def test_create_scan_job(self):
        from src.services.scanner import create_scan_job

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        site_id = uuid.uuid4()
        job = await create_scan_job(db, site_id=site_id, trigger="manual", max_pages=10)

        assert job.site_id == site_id
        assert job.status == "pending"
        assert job.trigger == "manual"
        assert job.pages_total == 10
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_scan_job(self):
        from src.services.scanner import start_scan_job

        db = AsyncMock()
        db.flush = AsyncMock()

        job = MagicMock()
        job.status = "pending"
        job.started_at = None

        result = await start_scan_job(db, job)

        assert result.status == "running"
        assert result.started_at is not None

    @pytest.mark.asyncio
    async def test_complete_scan_job_success(self):
        from src.services.scanner import complete_scan_job

        db = AsyncMock()
        db.flush = AsyncMock()

        job = MagicMock()
        result = await complete_scan_job(db, job, pages_scanned=5, cookies_found=10)

        assert result.status == "completed"
        assert result.pages_scanned == 5
        assert result.cookies_found == 10
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_complete_scan_job_failure(self):
        from src.services.scanner import complete_scan_job

        db = AsyncMock()
        db.flush = AsyncMock()

        job = MagicMock()
        result = await complete_scan_job(db, job, error_message="Connection failed")

        assert result.status == "failed"
        assert result.error_message == "Connection failed"

    @pytest.mark.asyncio
    async def test_add_scan_result(self):
        from src.services.scanner import add_scan_result

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        scan_job_id = uuid.uuid4()
        result = await add_scan_result(
            db,
            scan_job_id=scan_job_id,
            page_url="https://example.com",
            cookie_name="_ga",
            cookie_domain=".example.com",
            storage_type="cookie",
            auto_category="analytics",
        )

        assert result.scan_job_id == scan_job_id
        assert result.cookie_name == "_ga"
        assert result.auto_category == "analytics"
        db.add.assert_called_once()


class TestSitesDueForScan:
    """Test get_sites_due_for_scan: cron cadence + blank-schedule handling."""

    # A fixed "now": 14:00 UTC, well after the 03:00 daily fire time.
    NOW = datetime(2026, 6, 17, 14, 0, tzinfo=UTC)
    DAILY_AT_3AM = "0 3 * * *"

    def _site(self):
        site = MagicMock()
        site.id = uuid.uuid4()
        return site

    async def _run(self, rows, last_scan):
        """Invoke get_sites_due_for_scan with a mocked DB and last-scan time.

        ``last_scan`` is the time returned for every site in ``rows`` (or
        None to simulate a site that has never been scanned).
        """
        from src.services import scanner

        db = AsyncMock()
        result = MagicMock()
        result.all.return_value = rows
        db.execute = AsyncMock(return_value=result)

        times = {} if last_scan is None else {site.id: last_scan for site, _ in rows}
        with patch.object(scanner, "_last_scan_times", new=AsyncMock(return_value=times)):
            return await scanner.get_sites_due_for_scan(db, now=self.NOW)

    @pytest.mark.asyncio
    async def test_never_scanned_is_due(self):
        site = self._site()
        due = await self._run([(site, self.DAILY_AT_3AM)], last_scan=None)
        assert due == [site]

    @pytest.mark.asyncio
    async def test_scanned_after_last_fire_not_due(self):
        # Last scan at 05:00 today is after today's 03:00 fire — not due.
        site = self._site()
        last = datetime(2026, 6, 17, 5, 0, tzinfo=UTC)
        due = await self._run([(site, self.DAILY_AT_3AM)], last_scan=last)
        assert due == []

    @pytest.mark.asyncio
    async def test_scanned_before_last_fire_is_due(self):
        # Last scan yesterday evening predates today's 03:00 fire — due.
        site = self._site()
        last = datetime(2026, 6, 16, 20, 0, tzinfo=UTC)
        due = await self._run([(site, self.DAILY_AT_3AM)], last_scan=last)
        assert due == [site]

    @pytest.mark.asyncio
    async def test_blank_cron_never_due(self):
        # A non-NULL but blank schedule means "disabled" to the UI; it
        # must not be treated as an active schedule.
        site = self._site()
        due = await self._run([(site, "   ")], last_scan=None)
        assert due == []

    @pytest.mark.asyncio
    async def test_invalid_cron_skipped(self):
        site = self._site()
        due = await self._run([(site, "not a cron")], last_scan=None)
        assert due == []


# ── Router unit tests (mocked DB) ───────────────────────────────────


def _mock_auth_user():
    """Create a mock authenticated user."""
    from src.schemas.auth import CurrentUser

    return CurrentUser(
        id=uuid.uuid4(),
        organisation_id=uuid.uuid4(),
        email="test@example.com",
        role="owner",
    )


async def _authed_client(app, db, user=None):
    """Create an authenticated test client with mocked DB."""
    from src.db import get_db
    from src.services.dependencies import get_current_user

    if user is None:
        user = _mock_auth_user()

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: user

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestTriggerScan:
    """Test POST /scanner/scans."""

    @pytest.mark.asyncio
    async def test_trigger_scan_success(self, app):
        user = _mock_auth_user()
        db = AsyncMock()

        # Site exists and belongs to user's org
        site_mock = MagicMock()
        site_mock.organisation_id = user.organisation_id

        site_id = uuid.uuid4()
        job_id = uuid.uuid4()
        now = datetime.now(UTC)

        # Mock scan job returned by create_scan_job
        mock_job = MagicMock()
        mock_job.id = job_id
        mock_job.site_id = site_id
        mock_job.status = "pending"
        mock_job.trigger = "manual"
        mock_job.pages_scanned = 0
        mock_job.pages_total = 25
        mock_job.cookies_found = 0
        mock_job.error_message = None
        mock_job.started_at = None
        mock_job.completed_at = None
        mock_job.created_at = now
        mock_job.updated_at = now

        # First call: site lookup. Second call: running scan count.
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Site lookup
                result.scalar_one_or_none.return_value = site_mock
            elif call_count == 2:
                # Active scan jobs query — none running
                result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute
        db.add = MagicMock()
        db.flush = AsyncMock()

        with (
            patch(
                "src.routers.scanner.create_scan_job",
                new=AsyncMock(return_value=mock_job),
            ),
            patch("src.tasks.scanner.run_scan", create=True),
        ):
            async with await _authed_client(app, db, user) as client:
                resp = await client.post(
                    "/api/v1/scanner/scans",
                    json={
                        "site_id": str(site_id),
                        "max_pages": 25,
                    },
                )

        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_trigger_scan_site_not_found(self, app):
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)

        async with await _authed_client(app, db) as client:
            resp = await client.post(
                "/api/v1/scanner/scans",
                json={
                    "site_id": str(uuid.uuid4()),
                    "max_pages": 50,
                },
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_trigger_scan_conflict(self, app):
        user = _mock_auth_user()
        db = AsyncMock()

        # Build a non-stale active job so the router raises 409
        active_job = MagicMock()
        active_job.status = "running"
        active_job.created_at = datetime.now(UTC)
        active_job.started_at = datetime.now(UTC)

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Site lookup
                site_mock = MagicMock()
                site_mock.organisation_id = user.organisation_id
                result.scalar_one_or_none.return_value = site_mock
            elif call_count == 2:
                # Active scan jobs query — return a non-stale job
                result.scalars.return_value.all.return_value = [active_job]
            return result

        db.execute = mock_execute

        async with await _authed_client(app, db, user) as client:
            resp = await client.post(
                "/api/v1/scanner/scans",
                json={"site_id": str(uuid.uuid4())},
            )

        assert resp.status_code == 409


class TestListScans:
    """Test GET /scanner/scans/site/{site_id}."""

    @pytest.mark.asyncio
    async def test_list_scans_success(self, app):
        user = _mock_auth_user()
        db = AsyncMock()

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Site access check
                site_mock = MagicMock()
                site_mock.organisation_id = user.organisation_id
                result.scalar_one_or_none.return_value = site_mock
            else:
                # Scan list
                result.scalars.return_value.all.return_value = []
            return result

        db.execute = mock_execute

        async with await _authed_client(app, db, user) as client:
            resp = await client.get(f"/api/v1/scanner/scans/site/{uuid.uuid4()}")

        assert resp.status_code == 200
        assert resp.json() == []


class TestGetScan:
    """Test GET /scanner/scans/{scan_id}."""

    @pytest.mark.asyncio
    async def test_get_scan_not_found(self, app):
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)

        async with await _authed_client(app, db) as client:
            resp = await client.get(f"/api/v1/scanner/scans/{uuid.uuid4()}")

        assert resp.status_code == 404


class TestGetScanDiff:
    """Test GET /scanner/scans/{scan_id}/diff."""

    @pytest.mark.asyncio
    async def test_diff_scan_not_found(self, app):
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)

        async with await _authed_client(app, db) as client:
            resp = await client.get(f"/api/v1/scanner/scans/{uuid.uuid4()}/diff")

        assert resp.status_code == 404


# ── Integration tests ────────────────────────────────────────────────

try:
    from tests.conftest import create_test_site, requires_db
except ImportError:
    from conftest import create_test_site, requires_db


@requires_db
class TestScanIntegration:
    """Integration tests against a live database."""

    async def test_trigger_scan(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="scan-trigger")
        resp = await db_client.post(
            "/api/v1/scanner/scans",
            json={"site_id": site_id, "max_pages": 10},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["trigger"] == "manual"
        assert data["pages_total"] == 10

    async def test_trigger_scan_conflict(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="scan-conflict")
        # First scan
        resp1 = await db_client.post(
            "/api/v1/scanner/scans",
            json={"site_id": site_id},
            headers=auth_headers,
        )
        assert resp1.status_code == 201

        # Second scan — should conflict
        resp2 = await db_client.post(
            "/api/v1/scanner/scans",
            json={"site_id": site_id},
            headers=auth_headers,
        )
        assert resp2.status_code == 409

    async def test_list_scans(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="scan-list")
        # Trigger a scan
        await db_client.post(
            "/api/v1/scanner/scans",
            json={"site_id": site_id},
            headers=auth_headers,
        )

        resp = await db_client.get(
            f"/api/v1/scanner/scans/site/{site_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        scans = resp.json()
        assert len(scans) >= 1
        assert scans[0]["site_id"] == site_id

    async def test_get_scan_detail(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="scan-detail")
        create_resp = await db_client.post(
            "/api/v1/scanner/scans",
            json={"site_id": site_id},
            headers=auth_headers,
        )
        scan_id = create_resp.json()["id"]

        resp = await db_client.get(
            f"/api/v1/scanner/scans/{scan_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == scan_id
        assert "results" in data

    async def test_get_scan_diff(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="scan-diff")
        create_resp = await db_client.post(
            "/api/v1/scanner/scans",
            json={"site_id": site_id},
            headers=auth_headers,
        )
        scan_id = create_resp.json()["id"]

        resp = await db_client.get(
            f"/api/v1/scanner/scans/{scan_id}/diff",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_scan_id"] == scan_id
        # No previous scan, so previous_scan_id should be null
        assert data["previous_scan_id"] is None

    async def test_scan_not_found(self, db_client, auth_headers):
        resp = await db_client.get(
            f"/api/v1/scanner/scans/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_list_scans_pagination(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="scan-page")
        resp = await db_client.get(
            f"/api/v1/scanner/scans/site/{site_id}?limit=5&offset=0",
            headers=auth_headers,
        )
        assert resp.status_code == 200

    async def test_trigger_scan_requires_auth(self, db_client):
        resp = await db_client.post(
            "/api/v1/scanner/scans",
            json={"site_id": str(uuid.uuid4())},
        )
        assert resp.status_code in (401, 403)

    async def test_list_scans_requires_auth(self, db_client):
        resp = await db_client.get(f"/api/v1/scanner/scans/site/{uuid.uuid4()}")
        assert resp.status_code in (401, 403)
