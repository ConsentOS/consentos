"""Unit tests for sites router — mocked database."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import create_app
from src.services.auth import create_access_token

ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _auth_headers():
    token = create_access_token(
        user_id=USER_ID, organisation_id=ORG_ID, role="owner", email="admin@test.com"
    )
    return {"Authorization": f"Bearer {token}"}


def _mock_site(**overrides):
    site = MagicMock()
    site.id = overrides.get("id", uuid.uuid4())
    site.organisation_id = overrides.get("organisation_id", ORG_ID)
    site.domain = overrides.get("domain", "example.com")
    site.display_name = overrides.get("display_name", "Example Site")
    site.is_active = overrides.get("is_active", True)
    site.additional_domains = overrides.get("additional_domains")
    site.site_group_id = overrides.get("site_group_id")
    site.deleted_at = None
    site.created_at = datetime.now(UTC)
    site.updated_at = datetime.now(UTC)
    # Alias for SiteResponse.name field
    site.name = site.display_name
    return site


def _mock_config(**overrides):
    config = MagicMock(spec=[])  # spec=[] prevents auto-attr generation
    config.id = overrides.get("id", uuid.uuid4())
    config.site_id = overrides.get("site_id", uuid.uuid4())
    config.blocking_mode = overrides.get("blocking_mode", "opt_in")
    config.tcf_enabled = overrides.get("tcf_enabled", False)
    config.tcf_publisher_cc = overrides.get("tcf_publisher_cc")
    config.gpp_enabled = overrides.get("gpp_enabled", True)
    config.gpp_supported_apis = overrides.get("gpp_supported_apis", ["usnat"])
    config.gpc_enabled = overrides.get("gpc_enabled", True)
    default_jurisdictions = ["US-CA", "US-CO", "US-CT", "US-TX", "US-MT"]
    config.gpc_jurisdictions = overrides.get("gpc_jurisdictions", default_jurisdictions)
    config.gpc_global_honour = overrides.get("gpc_global_honour", False)
    config.gcm_enabled = overrides.get("gcm_enabled", True)
    config.gcm_default = overrides.get("gcm_default")
    config.banner_config = overrides.get("banner_config", {})
    config.regional_modes = overrides.get("regional_modes")
    config.privacy_policy_url = overrides.get("privacy_policy_url")
    config.scan_schedule_cron = overrides.get("scan_schedule_cron")
    config.scan_max_pages = overrides.get("scan_max_pages", 50)
    config.consent_expiry_days = overrides.get("consent_expiry_days", 365)
    config.consent_retention_days = overrides.get("consent_retention_days")
    config.terms_url = overrides.get("terms_url")
    config.shopify_privacy_enabled = overrides.get("shopify_privacy_enabled", False)
    config.regional_modes = overrides.get("regional_modes")
    config.enabled_categories = overrides.get("enabled_categories")
    config.disclosed_vendor_ids = overrides.get("disclosed_vendor_ids")
    config.created_at = datetime.now(UTC)
    config.updated_at = datetime.now(UTC)
    return config


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


def _mock_db_sequence(*results):
    """Create a mock session that returns different results on successive execute() calls."""
    session = AsyncMock()
    mock_results = []
    for r in results:
        result = MagicMock()
        if isinstance(r, list):
            result.scalar_one_or_none.return_value = r[0] if r else None
            scalars_obj = MagicMock()
            scalars_obj.all.return_value = r
            result.scalars.return_value = scalars_obj
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
            if hasattr(obj, "is_active") and getattr(obj, "is_active", None) is None:
                obj.is_active = True
            if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.now(UTC)
            if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
                obj.updated_at = datetime.now(UTC)

    session.flush = AsyncMock(side_effect=_fake_flush)
    session.refresh = AsyncMock()
    return session


class TestSiteCRUD:
    @pytest.mark.asyncio
    async def test_create_site_success(self, mock_app):
        # First execute: check existing (None), second: after flush
        db = _mock_db_sequence(None)  # no duplicate
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/sites/",
                json={"domain": "new-site.com", "display_name": "New Site"},
                headers=_auth_headers(),
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_site_duplicate(self, mock_app):
        existing_site = _mock_site(domain="dup.com")
        db = _mock_db_sequence(existing_site)
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/sites/",
                json={"domain": "dup.com", "display_name": "Dup Site"},
                headers=_auth_headers(),
            )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_list_sites(self, mock_app):
        sites = [_mock_site(), _mock_site(domain="two.com")]
        db = _mock_db_sequence(sites)
        async with await _client(mock_app, db) as client:
            resp = await client.get("/api/v1/sites/", headers=_auth_headers())
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_site_success(self, mock_app):
        site = _mock_site()
        db = _mock_db_sequence(site)
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/sites/{site.id}", headers=_auth_headers())
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_site_not_found(self, mock_app):
        db = _mock_db_sequence(None)
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/sites/{uuid.uuid4()}", headers=_auth_headers())
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_site(self, mock_app):
        site = _mock_site()
        db = _mock_db_sequence(site)
        async with await _client(mock_app, db) as client:
            resp = await client.patch(
                f"/api/v1/sites/{site.id}",
                json={"display_name": "Updated"},
                headers=_auth_headers(),
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_site(self, mock_app):
        site = _mock_site()
        db = _mock_db_sequence(site)
        async with await _client(mock_app, db) as client:
            resp = await client.delete(f"/api/v1/sites/{site.id}", headers=_auth_headers())
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_create_site_requires_auth(self, mock_app):
        db = _mock_db_sequence()
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/sites/", json={"domain": "noauth.com", "display_name": "No Auth"}
            )
        assert resp.status_code in (401, 403)


class TestSiteConfig:
    @pytest.mark.asyncio
    async def test_get_config_success(self, mock_app):
        site = _mock_site()
        config = _mock_config(site_id=site.id)
        # Extra Nones cover the cascade-loading queries: org defaults
        # and site_group_id lookup. Both being None means "no overrides
        # at parent layers, fall through to system defaults".
        db = _mock_db_sequence(site, config, None, None)
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/sites/{site.id}/config", headers=_auth_headers())
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_config_not_found(self, mock_app):
        site = _mock_site()
        db = _mock_db_sequence(site, None)
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/sites/{site.id}/config", headers=_auth_headers())
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_put_config_create(self, mock_app):
        site = _mock_site()
        # site found, no existing config, then cascade lookups (both None).
        db = _mock_db_sequence(site, None, None, None)
        async with await _client(mock_app, db) as client:
            resp = await client.put(
                f"/api/v1/sites/{site.id}/config",
                json={"blocking_mode": "opt_in"},
                headers=_auth_headers(),
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_put_config_replace(self, mock_app):
        site = _mock_site()
        config = _mock_config(site_id=site.id)
        db = _mock_db_sequence(site, config, None, None)
        async with await _client(mock_app, db) as client:
            resp = await client.put(
                f"/api/v1/sites/{site.id}/config",
                json={"blocking_mode": "opt_out"},
                headers=_auth_headers(),
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_patch_config_success(self, mock_app):
        site = _mock_site()
        config = _mock_config(site_id=site.id)
        db = _mock_db_sequence(site, config, None, None)
        async with await _client(mock_app, db) as client:
            resp = await client.patch(
                f"/api/v1/sites/{site.id}/config",
                json={"gcm_enabled": False, "consent_expiry_days": 180},
                headers=_auth_headers(),
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_patch_config_not_found(self, mock_app):
        site = _mock_site()
        db = _mock_db_sequence(site, None)
        async with await _client(mock_app, db) as client:
            resp = await client.patch(
                f"/api/v1/sites/{site.id}/config",
                json={"gcm_enabled": False},
                headers=_auth_headers(),
            )
        assert resp.status_code == 404
