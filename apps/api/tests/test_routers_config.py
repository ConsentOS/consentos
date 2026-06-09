"""Unit tests for config router — mocked database."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

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


def _mock_config(**overrides):
    config = MagicMock(spec=[])
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
    config.enabled_categories = overrides.get("enabled_categories")
    config.disclosed_vendor_ids = overrides.get("disclosed_vendor_ids")
    config.created_at = datetime.now(UTC)
    config.updated_at = datetime.now(UTC)
    return config


def _mock_db_sequence(*results):
    """Build a mock session that returns the given results in order.

    Each result is wrapped so both ``scalar_one_or_none()`` and ``all()``
    are accessible — the former returns the value, the latter an empty
    list (or a list when the value itself is a list). That lets the
    same mock satisfy both query styles used by the config router.
    """
    session = AsyncMock()
    mock_results = []
    for r in results:
        result = MagicMock()
        result.scalar_one_or_none.return_value = r
        result.all.return_value = r if isinstance(r, list) else []
        mock_results.append(result)
    session.execute = AsyncMock(side_effect=mock_results)
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


class TestPublicSiteConfig:
    @pytest.mark.asyncio
    async def test_get_public_config(self, mock_app):
        config = _mock_config()
        # Endpoint now applies the cascade: config row, then org_id,
        # org_config, group_id (all None for "no overrides").
        db = _mock_db_sequence(config, ORG_ID, None, None)
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/config/sites/{config.site_id}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_public_config_not_found(self, mock_app):
        db = _mock_db_sequence(None)
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/config/sites/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestResolvedConfig:
    @pytest.mark.asyncio
    async def test_get_resolved_config(self, mock_app):
        config = _mock_config()
        # Resolved endpoint queries: config, site org_id, org_config,
        # site group_id, gvl meta, category-purpose mapping.
        db = _mock_db_sequence(config, ORG_ID, None, None, None, [])
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/config/sites/{config.site_id}/resolved")
        assert resp.status_code == 200
        data = resp.json()
        assert "site_id" in data
        assert "blocking_mode" in data

    @pytest.mark.asyncio
    async def test_get_resolved_config_with_region(self, mock_app):
        config = _mock_config(regional_modes={"EU": "opt_in", "US": "opt_out"})
        db = _mock_db_sequence(config, ORG_ID, None, None, None, [])
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/config/sites/{config.site_id}/resolved?region=EU")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_resolved_config_not_found(self, mock_app):
        db = _mock_db_sequence(None)
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/config/sites/{uuid.uuid4()}/resolved")
        assert resp.status_code == 404


class TestPublishConfig:
    @pytest.mark.asyncio
    async def test_publish_config_success(self, mock_app):
        config = _mock_config()
        # Publish does: config query, org_config query, group_id, active A/B test query
        db = _mock_db_sequence(config, None, None, None)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.path = "/cdn/site-config.json"
        mock_result.published_at = datetime.now(UTC).isoformat()

        with patch(
            "src.routers.config.publish_site_config",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            async with await _client(mock_app, db) as client:
                resp = await client.post(
                    f"/api/v1/config/sites/{config.site_id}/publish",
                    headers=_auth_headers(),
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["published"] is True

    @pytest.mark.asyncio
    async def test_publish_config_failure(self, mock_app):
        config = _mock_config()
        db = _mock_db_sequence(config, None, None, None)

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "Disk full"

        with patch(
            "src.routers.config.publish_site_config",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            async with await _client(mock_app, db) as client:
                resp = await client.post(
                    f"/api/v1/config/sites/{config.site_id}/publish",
                    headers=_auth_headers(),
                )
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_publish_config_not_found(self, mock_app):
        db = _mock_db_sequence(None)
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                f"/api/v1/config/sites/{uuid.uuid4()}/publish",
                headers=_auth_headers(),
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_publish_requires_admin(self, mock_app):
        db = _mock_db_sequence()
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                f"/api/v1/config/sites/{uuid.uuid4()}/publish",
                headers=_auth_headers(role="viewer"),
            )
        assert resp.status_code == 403


class TestGeoResolvedConfig:
    @pytest.mark.asyncio
    async def test_get_geo_resolved_config_with_header(self, mock_app):
        config = _mock_config(
            regional_modes={"EU": "opt_in", "US": "opt_out", "DEFAULT": "informational"},
        )
        # Geo-resolved queries: config, site org_id, org_config,
        # site group_id, gvl meta, category-purpose mapping.
        db = _mock_db_sequence(config, ORG_ID, None, None, None, [])
        async with await _client(mock_app, db) as client:
            resp = await client.get(
                f"/api/v1/config/sites/{config.site_id}/geo-resolved",
                headers={"cf-ipcountry": "DE"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocking_mode"] == "opt_in"
        assert data["detected_country"] == "DE"
        assert data["detected_region"] == "EU"

    @pytest.mark.asyncio
    async def test_get_geo_resolved_config_us(self, mock_app):
        config = _mock_config(
            regional_modes={"EU": "opt_in", "US-CA": "opt_out", "DEFAULT": "informational"},
        )
        db = _mock_db_sequence(config, ORG_ID, None, None, None, [])

        with patch(
            "src.routers.config.detect_region",
            new_callable=AsyncMock,
        ) as mock_detect:
            from src.services.geoip import GeoResult

            mock_detect.return_value = GeoResult(country_code="US", region="US-CA")
            async with await _client(mock_app, db) as client:
                resp = await client.get(
                    f"/api/v1/config/sites/{config.site_id}/geo-resolved",
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocking_mode"] == "opt_out"
        assert data["detected_region"] == "US-CA"

    @pytest.mark.asyncio
    async def test_get_geo_resolved_config_not_found(self, mock_app):
        db = _mock_db_sequence(None)
        async with await _client(mock_app, db) as client:
            resp = await client.get(
                f"/api/v1/config/sites/{uuid.uuid4()}/geo-resolved",
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_geo_resolved_config_no_region_detected(self, mock_app):
        config = _mock_config(
            regional_modes={"EU": "opt_in", "DEFAULT": "informational"},
        )
        db = _mock_db_sequence(config, ORG_ID, None, None, None, [])

        with patch(
            "src.routers.config.detect_region",
            new_callable=AsyncMock,
        ) as mock_detect:
            from src.services.geoip import GeoResult

            mock_detect.return_value = GeoResult(country_code=None, region=None)
            async with await _client(mock_app, db) as client:
                resp = await client.get(
                    f"/api/v1/config/sites/{config.site_id}/geo-resolved",
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["detected_country"] is None
        assert data["detected_region"] is None


class TestVisitorGeo:
    @pytest.mark.asyncio
    async def test_get_visitor_geo_with_header(self, mock_app):
        db = _mock_db_sequence()
        async with await _client(mock_app, db) as client:
            resp = await client.get(
                "/api/v1/config/geo",
                headers={"cf-ipcountry": "GB"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["country_code"] == "GB"
        assert data["region"] == "GB"

    @pytest.mark.asyncio
    async def test_get_visitor_geo_no_headers(self, mock_app):
        db = _mock_db_sequence()

        with patch(
            "src.routers.config.detect_region",
            new_callable=AsyncMock,
        ) as mock_detect:
            from src.services.geoip import GeoResult

            mock_detect.return_value = GeoResult(country_code=None, region=None)
            async with await _client(mock_app, db) as client:
                resp = await client.get("/api/v1/config/geo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["country_code"] is None
        assert data["region"] is None
