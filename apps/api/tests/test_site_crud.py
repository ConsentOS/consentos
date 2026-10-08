"""Tests for site and site config CRUD endpoints and schemas."""

import uuid

import pytest
from pydantic import ValidationError

from src.schemas.site import (
    BlockingMode,
    SiteConfigCreate,
    SiteConfigResponse,
    SiteConfigUpdate,
    SiteCreate,
    SiteResponse,
    SiteUpdate,
)


class TestSiteSchemas:
    def test_create_valid(self):
        site = SiteCreate(domain="example.com", display_name="Example Site")
        assert site.domain == "example.com"

    def test_create_empty_domain_rejected(self):
        with pytest.raises(ValidationError):
            SiteCreate(domain="", display_name="Test")

    def test_update_partial(self):
        update = SiteUpdate(display_name="New Name")
        data = update.model_dump(exclude_unset=True)
        assert data == {"display_name": "New Name"}

    def test_response_from_attributes(self):
        now = "2026-01-01T00:00:00Z"
        resp = SiteResponse(
            id=uuid.uuid4(),
            organisation_id=uuid.uuid4(),
            domain="example.com",
            display_name="Example",
            is_active=True,
            additional_domains=None,
            created_at=now,
            updated_at=now,
        )
        assert resp.is_active


class TestSiteConfigSchemas:
    def test_create_defaults(self):
        config = SiteConfigCreate()
        assert config.blocking_mode == BlockingMode.OPT_IN
        assert config.gcm_enabled is True
        assert config.tcf_enabled is False
        assert config.scan_max_pages == 50
        assert config.consent_expiry_days == 365

    def test_create_with_regional_modes(self):
        config = SiteConfigCreate(
            regional_modes={"EU": "opt_in", "US-CA": "opt_out", "DEFAULT": "opt_in"}
        )
        assert config.regional_modes["EU"] == "opt_in"

    def test_scan_max_pages_bounds(self):
        with pytest.raises(ValidationError):
            SiteConfigCreate(scan_max_pages=0)
        with pytest.raises(ValidationError):
            SiteConfigCreate(scan_max_pages=1001)

    def test_consent_expiry_bounds(self):
        with pytest.raises(ValidationError):
            SiteConfigCreate(consent_expiry_days=0)
        with pytest.raises(ValidationError):
            SiteConfigCreate(consent_expiry_days=731)

    def test_update_partial(self):
        update = SiteConfigUpdate(blocking_mode=BlockingMode.OPT_OUT)
        data = update.model_dump(exclude_unset=True)
        assert data == {"blocking_mode": "opt_out"}

    def test_response_from_attributes(self):
        now = "2026-01-01T00:00:00Z"
        resp = SiteConfigResponse(
            id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            blocking_mode="opt_in",
            regional_modes=None,
            tcf_enabled=False,
            tcf_publisher_cc=None,
            gcm_enabled=True,
            gcm_default=None,
            banner_config=None,
            privacy_policy_url=None,
            scan_schedule_cron=None,
            scan_max_pages=50,
            consent_expiry_days=365,
            created_at=now,
            updated_at=now,
        )
        assert resp.blocking_mode == "opt_in"

    def test_display_mode_in_banner_config(self):
        """Display mode is stored inside banner_config, not as a top-level field."""
        config = SiteConfigCreate(
            banner_config={"displayMode": "overlay"},
        )
        assert config.banner_config is not None
        assert config.banner_config.displayMode == "overlay"


class TestEnums:
    def test_blocking_modes(self):
        assert BlockingMode.OPT_IN == "opt_in"
        assert BlockingMode.OPT_OUT == "opt_out"
        assert BlockingMode.INFORMATIONAL == "informational"


@pytest.mark.asyncio
class TestSiteRoutesRegistered:
    async def test_site_routes_exist(self, client):
        response = await client.get("/openapi.json")
        paths = response.json()["paths"]
        assert "/api/v1/sites/" in paths
        assert "/api/v1/sites/{site_id}" in paths
        assert "/api/v1/sites/{site_id}/config" in paths

    async def test_site_endpoints_require_auth(self, client):
        response = await client.get("/api/v1/sites/")
        assert response.status_code == 401

    async def test_site_config_endpoints_require_auth(self, client):
        site_id = uuid.uuid4()
        response = await client.get(f"/api/v1/sites/{site_id}/config")
        assert response.status_code == 401
