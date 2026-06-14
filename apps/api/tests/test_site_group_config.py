"""Tests for site group config endpoints."""

import uuid

import pytest

from tests.conftest import requires_db


class TestSiteGroupConfigRoutes:
    """Unit tests — no database required."""

    def test_group_config_get_route_registered(self, app):
        routes = list(app.openapi()["paths"])
        assert "/api/v1/site-groups/{group_id}/config" in routes

    def test_group_config_put_route_registered(self, app):
        routes = list(app.openapi()["paths"])
        assert "/api/v1/site-groups/{group_id}/config" in routes

    @pytest.mark.asyncio
    async def test_get_group_config_requires_auth(self, client):
        group_id = uuid.uuid4()
        resp = await client.get(f"/api/v1/site-groups/{group_id}/config")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_put_group_config_requires_auth(self, client):
        group_id = uuid.uuid4()
        resp = await client.put(
            f"/api/v1/site-groups/{group_id}/config",
            json={"blocking_mode": "opt_in"},
        )
        assert resp.status_code == 401


class TestSiteGroupConfigIntegration:
    """Integration tests — require a running PostgreSQL database."""

    @requires_db
    async def test_create_group_and_get_config(self, db_client, auth_headers):
        # Create a group
        resp = await db_client.post(
            "/api/v1/site-groups/",
            json={"name": f"test-group-{uuid.uuid4().hex[:8]}"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        group_id = resp.json()["id"]

        # GET config (auto-creates empty row)
        resp = await db_client.get(
            f"/api/v1/site-groups/{group_id}/config",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["site_group_id"] == group_id
        assert data["blocking_mode"] is None
        assert data["consent_expiry_days"] is None

    @requires_db
    async def test_update_group_config(self, db_client, auth_headers):
        # Create a group
        resp = await db_client.post(
            "/api/v1/site-groups/",
            json={"name": f"cfg-group-{uuid.uuid4().hex[:8]}"},
            headers=auth_headers,
        )
        group_id = resp.json()["id"]

        # PUT config
        resp = await db_client.put(
            f"/api/v1/site-groups/{group_id}/config",
            json={
                "blocking_mode": "opt_out",
                "consent_expiry_days": 90,
                "tcf_enabled": True,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocking_mode"] == "opt_out"
        assert data["consent_expiry_days"] == 90
        assert data["tcf_enabled"] is True

        # GET confirms persistence
        resp = await db_client.get(
            f"/api/v1/site-groups/{group_id}/config",
            headers=auth_headers,
        )
        data = resp.json()
        assert data["blocking_mode"] == "opt_out"
        assert data["consent_expiry_days"] == 90

    @requires_db
    async def test_group_config_not_found_for_other_org(self, db_client, auth_headers):
        fake_group_id = str(uuid.uuid4())
        resp = await db_client.get(
            f"/api/v1/site-groups/{fake_group_id}/config",
            headers=auth_headers,
        )
        assert resp.status_code == 404
