"""Unit tests for cookie, category, and allow-list routers — mocked database."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import create_app
from src.services.auth import create_access_token

ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _auth_headers(role="owner"):
    token = create_access_token(
        user_id=USER_ID, organisation_id=ORG_ID, role=role, email="admin@test.com"
    )
    return {"Authorization": f"Bearer {token}"}


def _mock_category(**overrides):
    cat = MagicMock(spec=[])
    cat.id = overrides.get("id", uuid.uuid4())
    cat.name = overrides.get("name", "Analytics")
    cat.slug = overrides.get("slug", "analytics")
    cat.description = overrides.get("description", "Analytics cookies")
    cat.is_essential = overrides.get("is_essential", False)
    cat.display_order = overrides.get("display_order", 3)
    cat.tcf_purpose_ids = overrides.get("tcf_purpose_ids", [])
    cat.gcm_consent_types = overrides.get("gcm_consent_types", ["analytics_storage"])
    cat.created_at = datetime.now(UTC)
    cat.updated_at = datetime.now(UTC)
    return cat


def _mock_cookie(**overrides):
    cookie = MagicMock(spec=[])
    cookie.id = overrides.get("id", uuid.uuid4())
    cookie.site_id = overrides.get("site_id", uuid.uuid4())
    cookie.name = overrides.get("name", "_ga")
    cookie.domain = overrides.get("domain", ".google.com")
    cookie.path = overrides.get("path", "/")
    cookie.category_id = overrides.get("category_id")
    cookie.storage_type = overrides.get("storage_type", "cookie")
    cookie.review_status = overrides.get("review_status", "pending")
    cookie.description = overrides.get("description")
    cookie.vendor = overrides.get("vendor")
    cookie.max_age_seconds = overrides.get("max_age_seconds")
    cookie.is_http_only = overrides.get("is_http_only")
    cookie.is_secure = overrides.get("is_secure")
    cookie.same_site = overrides.get("same_site")
    cookie.first_seen_at = overrides.get("first_seen_at", datetime.now(UTC).isoformat())
    cookie.last_seen_at = overrides.get("last_seen_at", datetime.now(UTC).isoformat())
    cookie.created_at = datetime.now(UTC)
    cookie.updated_at = datetime.now(UTC)
    return cookie


def _mock_site():
    site = MagicMock(spec=[])
    site.id = uuid.uuid4()
    site.organisation_id = ORG_ID
    site.domain = "test.com"
    site.deleted_at = None
    return site


def _mock_allow_list_entry(**overrides):
    entry = MagicMock(spec=[])
    entry.id = overrides.get("id", uuid.uuid4())
    entry.site_id = overrides.get("site_id", uuid.uuid4())
    entry.name_pattern = overrides.get("name_pattern", "_ga*")
    entry.domain_pattern = overrides.get("domain_pattern", ".google.com")
    entry.category_id = overrides.get("category_id", uuid.uuid4())
    entry.description = overrides.get("description")
    entry.created_at = datetime.now(UTC)
    entry.updated_at = datetime.now(UTC)
    return entry


def _mock_db_sequence(*results):
    session = AsyncMock()
    mock_results = []
    for r in results:
        result = MagicMock()
        if isinstance(r, list):
            result.scalar_one_or_none.return_value = r[0] if r else None
            scalars_obj = MagicMock()
            scalars_obj.all.return_value = r
            result.scalars.return_value = scalars_obj
        elif isinstance(r, dict) and "scalar" in r:
            result.scalar.return_value = r["scalar"]
        elif isinstance(r, dict) and "all" in r:
            result.all.return_value = r["all"]
        else:
            result.scalar_one_or_none.return_value = r
        mock_results.append(result)
    session.execute = AsyncMock(side_effect=mock_results)

    _added = []

    def _fake_add(obj):
        _added.append(obj)

    session.add = MagicMock(side_effect=_fake_add)

    async def _fake_flush():
        for obj in _added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            if hasattr(obj, "review_status") and getattr(obj, "review_status", None) is None:
                obj.review_status = "pending"
            if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.now(UTC)
            if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
                obj.updated_at = datetime.now(UTC)

    session.flush = AsyncMock(side_effect=_fake_flush)
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def mock_app():
    return create_app()


async def _client(app, mock_session):
    from src.db import get_db

    async def _override():
        yield mock_session

    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestCookieCategories:
    @pytest.mark.asyncio
    async def test_list_categories(self, mock_app):
        cats = [_mock_category(slug="necessary"), _mock_category(slug="analytics")]
        db = _mock_db_sequence(cats)
        async with await _client(mock_app, db) as client:
            resp = await client.get("/api/v1/cookies/categories")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_category(self, mock_app):
        cat = _mock_category()
        db = _mock_db_sequence(cat)
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/cookies/categories/{cat.id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_category_not_found(self, mock_app):
        db = _mock_db_sequence(None)
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/cookies/categories/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestCookieCRUD:
    @pytest.mark.asyncio
    async def test_list_cookies(self, mock_app):
        site = _mock_site()
        cookies = [_mock_cookie(site_id=site.id)]
        db = _mock_db_sequence(site, cookies)
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/cookies/sites/{site.id}", headers=_auth_headers())
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_cookies_empty(self, mock_app):
        site = _mock_site()
        db = _mock_db_sequence(site, [])
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/cookies/sites/{site.id}", headers=_auth_headers())
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_create_cookie(self, mock_app):
        site = _mock_site()
        db = _mock_db_sequence(site, None)  # site found, no existing duplicate
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                f"/api/v1/cookies/sites/{site.id}",
                json={"name": "_ga", "domain": ".google.com"},
                headers=_auth_headers(),
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_cookie_with_invalid_category(self, mock_app):
        site = _mock_site()
        cat_id = uuid.uuid4()
        db = _mock_db_sequence(site, None)  # site found, category not found
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                f"/api/v1/cookies/sites/{site.id}",
                json={"name": "_ga", "domain": ".google.com", "category_id": str(cat_id)},
                headers=_auth_headers(),
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_get_cookie(self, mock_app):
        site = _mock_site()
        cookie = _mock_cookie(site_id=site.id)
        db = _mock_db_sequence(site, cookie)
        async with await _client(mock_app, db) as client:
            resp = await client.get(
                f"/api/v1/cookies/sites/{site.id}/{cookie.id}",
                headers=_auth_headers(),
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_cookie_not_found(self, mock_app):
        site = _mock_site()
        db = _mock_db_sequence(site, None)
        async with await _client(mock_app, db) as client:
            resp = await client.get(
                f"/api/v1/cookies/sites/{site.id}/{uuid.uuid4()}",
                headers=_auth_headers(),
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_cookie(self, mock_app):
        site = _mock_site()
        cookie = _mock_cookie(site_id=site.id)
        db = _mock_db_sequence(site, cookie)
        async with await _client(mock_app, db) as client:
            resp = await client.patch(
                f"/api/v1/cookies/sites/{site.id}/{cookie.id}",
                json={"review_status": "approved"},
                headers=_auth_headers(),
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_cookie_not_found(self, mock_app):
        site = _mock_site()
        db = _mock_db_sequence(site, None)
        async with await _client(mock_app, db) as client:
            resp = await client.patch(
                f"/api/v1/cookies/sites/{site.id}/{uuid.uuid4()}",
                json={"review_status": "approved"},
                headers=_auth_headers(),
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_cookie_invalid_category(self, mock_app):
        site = _mock_site()
        cookie = _mock_cookie(site_id=site.id)
        cat_id = uuid.uuid4()
        # site found, cookie found, category validation fails
        db = _mock_db_sequence(site, cookie, None)
        async with await _client(mock_app, db) as client:
            resp = await client.patch(
                f"/api/v1/cookies/sites/{site.id}/{cookie.id}",
                json={"category_id": str(cat_id)},
                headers=_auth_headers(),
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_cookie(self, mock_app):
        site = _mock_site()
        cookie = _mock_cookie(site_id=site.id)
        db = _mock_db_sequence(site, cookie)
        async with await _client(mock_app, db) as client:
            resp = await client.delete(
                f"/api/v1/cookies/sites/{site.id}/{cookie.id}",
                headers=_auth_headers(),
            )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_cookie_not_found(self, mock_app):
        site = _mock_site()
        db = _mock_db_sequence(site, None)
        async with await _client(mock_app, db) as client:
            resp = await client.delete(
                f"/api/v1/cookies/sites/{site.id}/{uuid.uuid4()}",
                headers=_auth_headers(),
            )
        assert resp.status_code == 404


class TestCookieSummary:
    @pytest.mark.asyncio
    async def test_cookie_summary(self, mock_app):
        site = _mock_site()
        # summary makes 4 queries: _get_org_site, status count, category count, uncategorised
        db = _mock_db_sequence(
            site,
            {"all": [("pending", 5), ("approved", 3)]},
            {"all": [("analytics", 4), ("marketing", 2)]},
            {"scalar": 2},
        )
        async with await _client(mock_app, db) as client:
            resp = await client.get(
                f"/api/v1/cookies/sites/{site.id}/summary",
                headers=_auth_headers(),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "by_status" in data
        assert "uncategorised" in data


class TestAllowList:
    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_list_allow_list(self, mock_app):
        site = _mock_site()
        entries = [_mock_allow_list_entry(site_id=site.id)]
        db = _mock_db_sequence(site, entries)
        async with await _client(mock_app, db) as client:
            resp = await client.get(
                f"/api/v1/cookies/sites/{site.id}/allow-list",
                headers=_auth_headers(),
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_create_allow_list_entry(self, mock_app):
        site = _mock_site()
        cat = _mock_category()
        db = _mock_db_sequence(site, cat)  # site found, category valid
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                f"/api/v1/cookies/sites/{site.id}/allow-list",
                json={
                    "name_pattern": "_ga*",
                    "domain_pattern": ".google.com",
                    "category_id": str(cat.id),
                },
                headers=_auth_headers(),
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_allow_list_invalid_category(self, mock_app):
        site = _mock_site()
        db = _mock_db_sequence(site, None)  # site found, category not found
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                f"/api/v1/cookies/sites/{site.id}/allow-list",
                json={
                    "name_pattern": "_ga*",
                    "domain_pattern": ".google.com",
                    "category_id": str(uuid.uuid4()),
                },
                headers=_auth_headers(),
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_update_allow_list_entry(self, mock_app):
        site = _mock_site()
        entry = _mock_allow_list_entry(site_id=site.id)
        db = _mock_db_sequence(site, entry)
        async with await _client(mock_app, db) as client:
            resp = await client.patch(
                f"/api/v1/cookies/sites/{site.id}/allow-list/{entry.id}",
                json={"name_pattern": "_fbp*"},
                headers=_auth_headers(),
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_allow_list_not_found(self, mock_app):
        site = _mock_site()
        db = _mock_db_sequence(site, None)
        async with await _client(mock_app, db) as client:
            resp = await client.patch(
                f"/api/v1/cookies/sites/{site.id}/allow-list/{uuid.uuid4()}",
                json={"name_pattern": "_fbp*"},
                headers=_auth_headers(),
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_allow_list_invalid_category(self, mock_app):
        site = _mock_site()
        entry = _mock_allow_list_entry(site_id=site.id)
        db = _mock_db_sequence(site, entry, None)  # site, entry found, category invalid
        async with await _client(mock_app, db) as client:
            resp = await client.patch(
                f"/api/v1/cookies/sites/{site.id}/allow-list/{entry.id}",
                json={"category_id": str(uuid.uuid4())},
                headers=_auth_headers(),
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_allow_list_entry(self, mock_app):
        site = _mock_site()
        entry = _mock_allow_list_entry(site_id=site.id)
        db = _mock_db_sequence(site, entry)
        async with await _client(mock_app, db) as client:
            resp = await client.delete(
                f"/api/v1/cookies/sites/{site.id}/allow-list/{entry.id}",
                headers=_auth_headers(),
            )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_allow_list_not_found(self, mock_app):
        site = _mock_site()
        db = _mock_db_sequence(site, None)
        async with await _client(mock_app, db) as client:
            resp = await client.delete(
                f"/api/v1/cookies/sites/{site.id}/allow-list/{uuid.uuid4()}",
                headers=_auth_headers(),
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_site_not_found(self, mock_app):
        db = _mock_db_sequence(None)  # site not found
        async with await _client(mock_app, db) as client:
            resp = await client.get(
                f"/api/v1/cookies/sites/{uuid.uuid4()}",
                headers=_auth_headers(),
            )
        assert resp.status_code == 404
