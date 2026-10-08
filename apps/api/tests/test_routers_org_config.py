"""Unit tests for org-config router — mocked database."""

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


def _mock_org_config(**overrides):
    config = MagicMock()
    config.id = overrides.get("id", uuid.uuid4())
    config.organisation_id = overrides.get("organisation_id", ORG_ID)
    config.blocking_mode = overrides.get("blocking_mode")
    config.regional_modes = overrides.get("regional_modes")
    config.tcf_enabled = overrides.get("tcf_enabled")
    config.tcf_publisher_cc = overrides.get("tcf_publisher_cc")
    config.gcm_enabled = overrides.get("gcm_enabled")
    config.gcm_default = overrides.get("gcm_default")
    config.banner_config = overrides.get("banner_config")
    config.gpp_enabled = overrides.get("gpp_enabled")
    config.gpp_supported_apis = overrides.get("gpp_supported_apis")
    config.gpc_enabled = overrides.get("gpc_enabled")
    config.gpc_jurisdictions = overrides.get("gpc_jurisdictions")
    config.gpc_global_honour = overrides.get("gpc_global_honour")
    config.shopify_privacy_enabled = overrides.get("shopify_privacy_enabled")
    config.privacy_policy_url = overrides.get("privacy_policy_url")
    config.terms_url = overrides.get("terms_url")
    config.scan_schedule_cron = overrides.get("scan_schedule_cron")
    config.scan_max_pages = overrides.get("scan_max_pages")
    config.consent_expiry_days = overrides.get("consent_expiry_days")
    config.consent_retention_days = overrides.get("consent_retention_days")
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
    """Create a mock session returning different results on successive execute() calls."""
    session = AsyncMock()
    mock_results = []
    for r in results:
        result = MagicMock()
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
            if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.now(UTC)
            if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
                obj.updated_at = datetime.now(UTC)

    session.flush = AsyncMock(side_effect=_fake_flush)
    session.refresh = AsyncMock()
    return session


class TestGetOrgConfig:
    @pytest.mark.asyncio
    async def test_get_existing_config(self, mock_app):
        """GET /org-config/ returns existing config."""
        config = _mock_org_config(blocking_mode="opt_out", consent_expiry_days=180)
        db = _mock_db_sequence(config)
        async with await _client(mock_app, db) as client:
            resp = await client.get("/api/v1/org-config/", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocking_mode"] == "opt_out"
        assert data["consent_expiry_days"] == 180

    @pytest.mark.asyncio
    async def test_get_auto_creates_when_missing(self, mock_app):
        """GET /org-config/ auto-creates a blank config if none exists."""
        db = _mock_db_sequence(None)  # no existing config
        async with await _client(mock_app, db) as client:
            resp = await client.get("/api/v1/org-config/", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        # All optional fields should be None
        assert data["blocking_mode"] is None
        assert data["tcf_enabled"] is None

    @pytest.mark.asyncio
    async def test_get_requires_auth(self, mock_app):
        """GET /org-config/ returns 401 without token."""
        db = _mock_db_sequence()
        async with await _client(mock_app, db) as client:
            resp = await client.get("/api/v1/org-config/")
        assert resp.status_code == 401


class TestUpdateOrgConfig:
    @pytest.mark.asyncio
    async def test_update_existing_config(self, mock_app):
        """PUT /org-config/ updates existing config."""
        config = _mock_org_config()
        db = _mock_db_sequence(config)
        async with await _client(mock_app, db) as client:
            resp = await client.put(
                "/api/v1/org-config/",
                json={"blocking_mode": "opt_out", "consent_expiry_days": 90},
                headers=_auth_headers(),
            )
        assert resp.status_code == 200
        # Verify setattr was called on the mock
        assert config.blocking_mode == "opt_out"
        assert config.consent_expiry_days == 90

    @pytest.mark.asyncio
    async def test_update_creates_when_missing(self, mock_app):
        """PUT /org-config/ creates config if none exists."""
        db = _mock_db_sequence(None)  # no existing config
        async with await _client(mock_app, db) as client:
            resp = await client.put(
                "/api/v1/org-config/",
                json={"tcf_enabled": True},
                headers=_auth_headers(),
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_requires_admin(self, mock_app):
        """PUT /org-config/ returns 403 for viewers."""
        db = _mock_db_sequence()
        async with await _client(mock_app, db) as client:
            resp = await client.put(
                "/api/v1/org-config/",
                json={"blocking_mode": "opt_in"},
                headers=_auth_headers(role="viewer"),
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_allows_editor_role_fails(self, mock_app):
        """PUT /org-config/ returns 403 for editors (only owner/admin can update)."""
        db = _mock_db_sequence()
        async with await _client(mock_app, db) as client:
            resp = await client.put(
                "/api/v1/org-config/",
                json={"blocking_mode": "opt_in"},
                headers=_auth_headers(role="editor"),
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_stores_banner_config_as_sent(self, mock_app):
        """PUT /org-config/ stores only the banner keys that were sent."""
        config = _mock_org_config()
        db = _mock_db_sequence(config)
        banner = {"primaryColour": "#2563eb", "show_reject_all": True}
        async with await _client(mock_app, db) as client:
            resp = await client.put(
                "/api/v1/org-config/",
                json={"banner_config": banner, "privacy_policy_url": "https://example.com/p"},
                headers=_auth_headers(),
            )
        assert resp.status_code == 200
        assert config.banner_config == banner
        assert config.privacy_policy_url == "https://example.com/p"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "body",
        [
            {"banner_config": {"primaryColour": "red; } body {"}},
            {"banner_config": {"fontFamily": "Arial; color: red"}},
            {"banner_config": {"acceptButton": {"textColour": "url(x)"}}},
            {"privacy_policy_url": "javascript:void(0)"},
            {"terms_url": "data:text/html,hi"},
            {"privacy_policy_url": "//example.com/privacy"},
        ],
    )
    async def test_update_rejects_invalid_banner_values(self, mock_app, body):
        """PUT /org-config/ returns 422 for invalid colours, fonts and URLs."""
        db = _mock_db_sequence()
        async with await _client(mock_app, db) as client:
            resp = await client.put("/api/v1/org-config/", json=body, headers=_auth_headers())
        assert resp.status_code == 422
