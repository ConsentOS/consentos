"""Tests for scanner cookie report endpoint — CMP-23 (API side).

Covers:
  - Schema validation
  - Report endpoint (unit tests with mocked DB)
  - Integration tests against live database
"""

import logging
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.schemas.scanner import (
    CookieReportRequest,
    CookieReportResponse,
    ReportedCookie,
    ScanStatus,
    ScanTrigger,
)

# ── Schema tests ─────────────────────────────────────────────────────


class TestSchemas:
    """Validate scanner schemas."""

    def test_scan_status_values(self):
        assert ScanStatus.PENDING == "pending"
        assert ScanStatus.COMPLETED == "completed"

    def test_scan_trigger_values(self):
        assert ScanTrigger.CLIENT_REPORT == "client_report"

    def test_reported_cookie(self):
        rc = ReportedCookie(
            name="_ga",
            domain=".example.com",
            storage_type="cookie",
            value_length=30,
        )
        assert rc.name == "_ga"

    def test_reported_cookie_validation(self):
        with pytest.raises(ValueError):
            ReportedCookie(name="", domain=".example.com")

    def test_cookie_report_request(self):
        req = CookieReportRequest(
            site_id=uuid.uuid4(),
            page_url="https://example.com/page",
            cookies=[
                ReportedCookie(name="_ga", domain=".example.com"),
            ],
            collected_at=datetime.now(),
        )
        assert len(req.cookies) == 1

    def test_cookie_report_response(self):
        resp = CookieReportResponse(
            accepted=True,
            cookies_received=5,
            new_cookies=2,
        )
        assert resp.new_cookies == 2


# ── Router unit tests (mocked DB) ───────────────────────────────────


def _mock_site(domain="example.com", additional_domains=None):
    site = MagicMock()
    site.id = uuid.uuid4()
    site.domain = domain
    site.additional_domains = additional_domains
    return site


def _report(page_url="https://example.com", cookies=None):
    return {
        "site_id": str(uuid.uuid4()),
        "page_url": page_url,
        "cookies": cookies or [],
        "collected_at": datetime.now().isoformat(),
    }


def _mock_db_with_site(site_mock=None):
    """Create a mock DB that returns a site for validation."""
    db = AsyncMock()
    site_mock = site_mock or _mock_site()
    cookie_result = MagicMock()
    cookie_result.scalar_one_or_none.return_value = None  # no existing cookie

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Site validation
            result = MagicMock()
            result.scalar_one_or_none.return_value = site_mock
            return result
        # Cookie existence checks
        return cookie_result

    db.execute = mock_execute
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


async def _client(app, db):
    from src.db import get_db

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestReportEndpoint:
    """Test POST /scanner/report."""

    @pytest.mark.asyncio
    async def test_report_success(self, app):
        db = _mock_db_with_site()
        async with await _client(app, db) as client:
            resp = await client.post(
                "/api/v1/scanner/report",
                json={
                    "site_id": str(uuid.uuid4()),
                    "page_url": "https://example.com",
                    "cookies": [
                        {
                            "name": "_ga",
                            "domain": ".example.com",
                            "storage_type": "cookie",
                            "value_length": 30,
                        },
                    ],
                    "collected_at": datetime.now().isoformat(),
                },
            )
        assert resp.status_code == 202
        data = resp.json()
        assert data["accepted"] is True
        assert data["cookies_received"] == 1

    @pytest.mark.asyncio
    async def test_report_site_not_found(self, app):
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        async with await _client(app, db) as client:
            resp = await client.post(
                "/api/v1/scanner/report",
                json={
                    "site_id": str(uuid.uuid4()),
                    "page_url": "https://example.com",
                    "cookies": [],
                    "collected_at": datetime.now().isoformat(),
                },
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_report_empty_cookies(self, app):
        db = AsyncMock()
        site_result = MagicMock()
        site_result.scalar_one_or_none.return_value = _mock_site()
        db.execute.return_value = site_result
        db.flush = AsyncMock()

        async with await _client(app, db) as client:
            resp = await client.post(
                "/api/v1/scanner/report",
                json={
                    "site_id": str(uuid.uuid4()),
                    "page_url": "https://example.com",
                    "cookies": [],
                    "collected_at": datetime.now().isoformat(),
                },
            )
        assert resp.status_code == 202
        assert resp.json()["cookies_received"] == 0

    @pytest.mark.asyncio
    async def test_report_multiple_storage_types(self, app):
        db = _mock_db_with_site()
        async with await _client(app, db) as client:
            resp = await client.post(
                "/api/v1/scanner/report",
                json={
                    "site_id": str(uuid.uuid4()),
                    "page_url": "https://example.com",
                    "cookies": [
                        {
                            "name": "_ga",
                            "domain": ".example.com",
                            "storage_type": "cookie",
                            "value_length": 30,
                        },
                        {
                            "name": "analytics_id",
                            "domain": "example.com",
                            "storage_type": "local_storage",
                            "value_length": 10,
                        },
                        {
                            "name": "session_key",
                            "domain": "example.com",
                            "storage_type": "session_storage",
                            "value_length": 20,
                        },
                    ],
                    "collected_at": datetime.now().isoformat(),
                },
            )
        assert resp.status_code == 202
        assert resp.json()["cookies_received"] == 3

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "page_url",
        ["https://other.test/page", "https://example.com.other.test/", "not a url", ""],
    )
    async def test_report_page_url_outside_site_rejected(self, app, page_url):
        db = _mock_db_with_site()
        async with await _client(app, db) as client:
            resp = await client.post("/api/v1/scanner/report", json=_report(page_url))
        assert resp.status_code == 403
        db.add.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "headers",
        [{"origin": "https://other.test"}, {"referer": "https://other.test/page"}],
    )
    async def test_report_origin_outside_site_rejected(self, app, headers):
        db = _mock_db_with_site()
        async with await _client(app, db) as client:
            resp = await client.post("/api/v1/scanner/report", headers=headers, json=_report())
        assert resp.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("headers", "page_url", "rejected_host"),
        [
            ({"origin": "https://other.test"}, "https://example.com/", "other.test"),
            ({}, "https://elsewhere.test/basket?id=1", "elsewhere.test"),
        ],
    )
    async def test_report_rejection_logged(self, app, caplog, headers, page_url, rejected_host):
        site = _mock_site()
        db = _mock_db_with_site(site)
        with caplog.at_level(logging.WARNING, logger="src.services.site_domains"):
            async with await _client(app, db) as client:
                resp = await client.post(
                    "/api/v1/scanner/report", headers=headers, json=_report(page_url)
                )
        assert resp.status_code == 403
        [record] = [r for r in caplog.records if r.name == "src.services.site_domains"]
        assert record.levelno == logging.WARNING
        message = record.getMessage()
        assert str(site.id) in message
        assert rejected_host in message
        assert "https://" not in message
        assert "basket" not in message

    @pytest.mark.asyncio
    async def test_report_null_origin_falls_back_to_page_url(self, app):
        db = _mock_db_with_site()
        async with await _client(app, db) as client:
            resp = await client.post(
                "/api/v1/scanner/report", headers={"origin": "null"}, json=_report()
            )
        assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_report_matching_subdomain_origin_accepted(self, app):
        db = _mock_db_with_site()
        async with await _client(app, db) as client:
            resp = await client.post(
                "/api/v1/scanner/report",
                headers={"origin": "https://shop.example.com"},
                json=_report("https://shop.example.com/basket"),
            )
        assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_report_drops_cookies_outside_site_domains(self, app):
        db = _mock_db_with_site()
        cookies = [
            {"name": "_ga", "domain": ".example.com"},
            {"name": "sub", "domain": "shop.example.com"},
            {"name": "foreign", "domain": ".other.test"},
            {"name": "lookalike", "domain": "notexample.com"},
        ]
        async with await _client(app, db) as client:
            resp = await client.post("/api/v1/scanner/report", json=_report(cookies=cookies))
        assert resp.status_code == 202
        data = resp.json()
        assert data["cookies_received"] == 4
        assert data["new_cookies"] == 2
        added = {call.args[0].name for call in db.add.call_args_list}
        assert added == {"_ga", "sub"}


# ── Integration tests ────────────────────────────────────────────────


try:
    from tests.conftest import create_test_site, requires_db
except ImportError:
    from conftest import create_test_site, requires_db


async def _create_site(client, headers, prefix: str) -> tuple[str, str]:
    """Create a site and return its ID and domain."""
    site_id = await create_test_site(client, headers, domain_prefix=prefix)
    resp = await client.get(f"/api/v1/sites/{site_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return site_id, resp.json()["domain"]


@requires_db
class TestScannerReportIntegration:
    """Integration tests against a live database."""

    async def test_report_creates_new_cookies(self, db_client, auth_headers):
        site_id, domain = await _create_site(db_client, auth_headers, "report-new")
        resp = await db_client.post(
            "/api/v1/scanner/report",
            json={
                "site_id": site_id,
                "page_url": f"https://{domain}/page",
                "cookies": [
                    {
                        "name": "_ga",
                        "domain": f".{domain}",
                        "storage_type": "cookie",
                        "value_length": 30,
                    },
                    {
                        "name": "analytics_id",
                        "domain": domain,
                        "storage_type": "local_storage",
                        "value_length": 10,
                    },
                ],
                "collected_at": datetime.now().isoformat(),
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["cookies_received"] == 2
        assert data["new_cookies"] == 2

        # Verify cookies were created
        cookies_resp = await db_client.get(
            f"/api/v1/cookies/sites/{site_id}",
            headers=auth_headers,
        )
        assert cookies_resp.status_code == 200
        cookies = cookies_resp.json()
        names = [c["name"] for c in cookies]
        assert "_ga" in names
        assert "analytics_id" in names

    async def test_report_deduplicates_existing_cookies(self, db_client, auth_headers):
        site_id, domain = await _create_site(db_client, auth_headers, "report-dedup")
        report_payload = {
            "site_id": site_id,
            "page_url": f"https://{domain}",
            "cookies": [
                {
                    "name": "_dedup_cookie",
                    "domain": f".{domain}",
                    "storage_type": "cookie",
                    "value_length": 10,
                },
            ],
            "collected_at": datetime.now().isoformat(),
        }

        # First report — should create
        resp1 = await db_client.post("/api/v1/scanner/report", json=report_payload)
        assert resp1.status_code == 202
        assert resp1.json()["new_cookies"] == 1

        # Second report — should not create duplicate
        resp2 = await db_client.post("/api/v1/scanner/report", json=report_payload)
        assert resp2.status_code == 202
        assert resp2.json()["new_cookies"] == 0

    async def test_report_sets_review_status_pending(self, db_client, auth_headers):
        site_id, domain = await _create_site(db_client, auth_headers, "report-status")
        await db_client.post(
            "/api/v1/scanner/report",
            json={
                "site_id": site_id,
                "page_url": f"https://{domain}",
                "cookies": [
                    {
                        "name": "_status_cookie",
                        "domain": f".{domain}",
                        "storage_type": "cookie",
                        "value_length": 5,
                    },
                ],
                "collected_at": datetime.now().isoformat(),
            },
        )
        # Check the created cookie's review status
        cookies_resp = await db_client.get(
            f"/api/v1/cookies/sites/{site_id}",
            headers=auth_headers,
        )
        cookies = cookies_resp.json()
        status_cookie = next((c for c in cookies if c["name"] == "_status_cookie"), None)
        assert status_cookie is not None
        assert status_cookie["review_status"] == "pending"

    async def test_report_no_auth_required(self, db_client, auth_headers):
        """Report endpoint should work without authentication."""
        site_id, domain = await _create_site(db_client, auth_headers, "report-noauth")
        # POST without auth headers
        resp = await db_client.post(
            "/api/v1/scanner/report",
            json={
                "site_id": site_id,
                "page_url": f"https://{domain}",
                "cookies": [],
                "collected_at": datetime.now().isoformat(),
            },
        )
        assert resp.status_code == 202

    async def test_report_invalid_site(self, db_client):
        resp = await db_client.post(
            "/api/v1/scanner/report",
            json={
                "site_id": str(uuid.uuid4()),
                "page_url": "https://unknown.com",
                "cookies": [],
                "collected_at": datetime.now().isoformat(),
            },
        )
        assert resp.status_code == 404

    async def test_report_inactive_site_returns_404(self, db_client, auth_headers):
        site_id, domain = await _create_site(db_client, auth_headers, "report-inactive")
        resp = await db_client.patch(
            f"/api/v1/sites/{site_id}", json={"is_active": False}, headers=auth_headers
        )
        assert resp.status_code == 200
        resp = await db_client.post(
            "/api/v1/scanner/report",
            json={
                "site_id": site_id,
                "page_url": f"https://{domain}/",
                "cookies": [{"name": "_ga", "domain": f".{domain}"}],
                "collected_at": datetime.now().isoformat(),
            },
        )
        assert resp.status_code == 404

    async def test_report_rejects_page_url_outside_site(self, db_client, auth_headers):
        site_id, _ = await _create_site(db_client, auth_headers, "report-foreign-page")
        resp = await db_client.post(
            "/api/v1/scanner/report",
            json={
                "site_id": site_id,
                "page_url": "https://elsewhere.test/",
                "cookies": [],
                "collected_at": datetime.now().isoformat(),
            },
        )
        assert resp.status_code == 403

    async def test_report_ignores_cookies_outside_site(self, db_client, auth_headers):
        site_id, domain = await _create_site(db_client, auth_headers, "report-foreign")
        resp = await db_client.post(
            "/api/v1/scanner/report",
            headers={"origin": f"https://www.{domain}"},
            json={
                "site_id": site_id,
                "page_url": f"https://www.{domain}/",
                "cookies": [
                    {"name": "_own", "domain": f".{domain}"},
                    {"name": "_foreign", "domain": ".elsewhere.test"},
                ],
                "collected_at": datetime.now().isoformat(),
            },
        )
        assert resp.status_code == 202
        assert resp.json()["new_cookies"] == 1
        cookies_resp = await db_client.get(f"/api/v1/cookies/sites/{site_id}", headers=auth_headers)
        names = {c["name"] for c in cookies_resp.json()}
        assert names == {"_own"}
