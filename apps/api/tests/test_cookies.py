"""Tests for cookie category, cookie, and allow-list schemas and routes."""

import uuid

import pytest
from pydantic import ValidationError

from src.schemas.cookie import (
    AllowListEntryCreate,
    AllowListEntryUpdate,
    CookieCategoryResponse,
    CookieCreate,
    CookieResponse,
    CookieUpdate,
    ReviewStatus,
    StorageType,
)

# ─── Schema tests ────────────────────────────────────────────────────


class TestStorageType:
    def test_values(self):
        assert StorageType.cookie == "cookie"
        assert StorageType.local_storage == "local_storage"
        assert StorageType.session_storage == "session_storage"
        assert StorageType.indexed_db == "indexed_db"


class TestReviewStatus:
    def test_values(self):
        assert ReviewStatus.pending == "pending"
        assert ReviewStatus.approved == "approved"
        assert ReviewStatus.rejected == "rejected"


class TestCookieCreate:
    def test_valid_minimal(self):
        schema = CookieCreate(name="_ga", domain=".example.com")
        assert schema.name == "_ga"
        assert schema.domain == ".example.com"
        assert schema.storage_type == StorageType.cookie
        assert schema.category_id is None

    def test_valid_full(self):
        cat_id = uuid.uuid4()
        schema = CookieCreate(
            name="_ga",
            domain=".google.com",
            storage_type=StorageType.cookie,
            category_id=cat_id,
            description="Google Analytics cookie",
            vendor="Google",
            path="/",
            max_age_seconds=63072000,
            is_http_only=False,
            is_secure=True,
            same_site="Lax",
        )
        assert schema.category_id == cat_id
        assert schema.max_age_seconds == 63072000

    def test_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            CookieCreate(name="", domain=".example.com")

    def test_rejects_empty_domain(self):
        with pytest.raises(ValidationError):
            CookieCreate(name="_ga", domain="")


class TestCookieUpdate:
    def test_partial_update(self):
        schema = CookieUpdate(review_status=ReviewStatus.approved)
        dump = schema.model_dump(exclude_unset=True)
        assert dump == {"review_status": ReviewStatus.approved}

    def test_update_category(self):
        cat_id = uuid.uuid4()
        schema = CookieUpdate(category_id=cat_id)
        assert schema.category_id == cat_id


class TestAllowListEntryCreate:
    def test_valid(self):
        cat_id = uuid.uuid4()
        schema = AllowListEntryCreate(
            name_pattern="_ga*",
            domain_pattern=".google.com",
            category_id=cat_id,
            description="Google Analytics cookies",
        )
        assert schema.name_pattern == "_ga*"
        assert schema.category_id == cat_id

    def test_rejects_empty_name_pattern(self):
        with pytest.raises(ValidationError):
            AllowListEntryCreate(
                name_pattern="",
                domain_pattern=".example.com",
                category_id=uuid.uuid4(),
            )


class TestAllowListEntryUpdate:
    def test_partial_update(self):
        schema = AllowListEntryUpdate(description="Updated description")
        dump = schema.model_dump(exclude_unset=True)
        assert dump == {"description": "Updated description"}


class TestCookieCategoryResponse:
    def test_from_dict(self):
        now = "2024-01-01T00:00:00"
        resp = CookieCategoryResponse(
            id=uuid.uuid4(),
            name="Analytics",
            slug="analytics",
            description="Analytics cookies",
            is_essential=False,
            display_order=2,
            tcf_purpose_ids=[1, 3],
            gcm_consent_types=["analytics_storage"],
            created_at=now,
            updated_at=now,
        )
        assert resp.slug == "analytics"
        assert resp.is_essential is False


class TestCookieResponse:
    def test_from_dict(self):
        now = "2024-01-01T00:00:00"
        resp = CookieResponse(
            id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            name="_ga",
            domain=".google.com",
            storage_type="cookie",
            review_status="pending",
            created_at=now,
            updated_at=now,
        )
        assert resp.name == "_ga"
        assert resp.review_status == "pending"


# ─── Route tests ─────────────────────────────────────────────────────


class TestCookieCategoryRoutes:
    def test_categories_route_registered(self, app):
        """Verify the categories routes are registered in the app."""
        routes = list(app.openapi()["paths"])
        assert "/api/v1/cookies/categories" in routes
        assert "/api/v1/cookies/categories/{category_id}" in routes


class TestCookieRoutes:
    @pytest.mark.asyncio
    async def test_list_cookies_requires_auth(self, client):
        site_id = uuid.uuid4()
        resp = await client.get(f"/api/v1/cookies/sites/{site_id}")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_cookie_requires_auth(self, client):
        site_id = uuid.uuid4()
        resp = await client.post(
            f"/api/v1/cookies/sites/{site_id}",
            json={"name": "_ga", "domain": ".google.com"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_cookie_rejects_invalid_body(self, client):
        site_id = uuid.uuid4()
        resp = await client.post(
            f"/api/v1/cookies/sites/{site_id}",
            json={"name": "", "domain": ""},
            headers={"Authorization": "Bearer fake-token"},
        )
        # Should return 401 (bad token) or 422 (validation)
        assert resp.status_code in (401, 422)

    @pytest.mark.asyncio
    async def test_summary_route_requires_auth(self, client):
        site_id = uuid.uuid4()
        resp = await client.get(f"/api/v1/cookies/sites/{site_id}/summary")
        assert resp.status_code == 401


class TestAllowListRoutes:
    @pytest.mark.asyncio
    async def test_list_allow_list_requires_auth(self, client):
        site_id = uuid.uuid4()
        resp = await client.get(f"/api/v1/cookies/sites/{site_id}/allow-list")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_allow_list_requires_auth(self, client):
        site_id = uuid.uuid4()
        resp = await client.post(
            f"/api/v1/cookies/sites/{site_id}/allow-list",
            json={
                "name_pattern": "_ga*",
                "domain_pattern": ".google.com",
                "category_id": str(uuid.uuid4()),
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_allow_list_requires_auth(self, client):
        site_id = uuid.uuid4()
        entry_id = uuid.uuid4()
        resp = await client.delete(f"/api/v1/cookies/sites/{site_id}/allow-list/{entry_id}")
        assert resp.status_code == 401
