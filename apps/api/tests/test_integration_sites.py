"""Integration tests for site and site config endpoints (requires database)."""

import uuid

from tests.conftest import requires_db


@requires_db
class TestSiteCRUD:
    async def test_create_site(self, db_client, auth_headers):
        domain = f"example-{uuid.uuid4().hex[:8]}.com"
        resp = await db_client.post(
            "/api/v1/sites/",
            json={
                "domain": domain,
                "display_name": "Example Site",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["domain"] == domain
        assert data["display_name"] == "Example Site"
        assert data["is_active"] is True
        assert "id" in data

    async def test_create_site_duplicate_domain(self, db_client, auth_headers):
        domain = f"dup-{uuid.uuid4().hex[:8]}.com"
        # Create first
        await db_client.post(
            "/api/v1/sites/",
            json={
                "domain": domain,
                "display_name": "Dup Test",
            },
            headers=auth_headers,
        )
        # Duplicate should fail
        resp = await db_client.post(
            "/api/v1/sites/",
            json={
                "domain": domain,
                "display_name": "Dup Test",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 409

    async def test_list_sites(self, db_client, auth_headers):
        resp = await db_client.get("/api/v1/sites/", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_get_site(self, db_client, auth_headers):
        # Create a site first
        domain = f"get-{uuid.uuid4().hex[:8]}.com"
        create_resp = await db_client.post(
            "/api/v1/sites/",
            json={
                "domain": domain,
                "display_name": "Get Test",
            },
            headers=auth_headers,
        )
        site_id = create_resp.json()["id"]

        resp = await db_client.get(f"/api/v1/sites/{site_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["domain"] == domain

    async def test_get_site_not_found(self, db_client, auth_headers):
        resp = await db_client.get(
            f"/api/v1/sites/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_update_site(self, db_client, auth_headers):
        domain = f"update-{uuid.uuid4().hex[:8]}.com"
        create_resp = await db_client.post(
            "/api/v1/sites/",
            json={
                "domain": domain,
                "display_name": "Update Test",
            },
            headers=auth_headers,
        )
        site_id = create_resp.json()["id"]

        resp = await db_client.patch(
            f"/api/v1/sites/{site_id}",
            json={"display_name": "Updated Name"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Updated Name"

    async def test_delete_site_soft_deletes(self, db_client, auth_headers):
        domain = f"delete-{uuid.uuid4().hex[:8]}.com"
        create_resp = await db_client.post(
            "/api/v1/sites/",
            json={
                "domain": domain,
                "display_name": "Delete Test",
            },
            headers=auth_headers,
        )
        site_id = create_resp.json()["id"]

        resp = await db_client.delete(f"/api/v1/sites/{site_id}", headers=auth_headers)
        assert resp.status_code == 204

        # Should no longer be findable
        get_resp = await db_client.get(f"/api/v1/sites/{site_id}", headers=auth_headers)
        assert get_resp.status_code == 404

    async def test_create_site_requires_auth(self, db_client):
        resp = await db_client.post(
            "/api/v1/sites/",
            json={
                "domain": "noauth.com",
                "display_name": "No Auth",
            },
        )
        assert resp.status_code == 401


@requires_db
class TestSiteConfig:
    async def test_get_config_creates_default(self, db_client, auth_headers):
        domain = f"config-{uuid.uuid4().hex[:8]}.com"
        create_resp = await db_client.post(
            "/api/v1/sites/",
            json={
                "domain": domain,
                "display_name": "Config Test",
            },
            headers=auth_headers,
        )
        site_id = create_resp.json()["id"]

        # PUT config to create it
        put_resp = await db_client.put(
            f"/api/v1/sites/{site_id}/config",
            json={"blocking_mode": "opt_in"},
            headers=auth_headers,
        )
        assert put_resp.status_code in (200, 201)

        # GET config
        resp = await db_client.get(
            f"/api/v1/sites/{site_id}/config",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocking_mode"] == "opt_in"

    async def test_update_config(self, db_client, auth_headers):
        domain = f"config-upd-{uuid.uuid4().hex[:8]}.com"
        create_resp = await db_client.post(
            "/api/v1/sites/",
            json={
                "domain": domain,
                "display_name": "Config Update",
            },
            headers=auth_headers,
        )
        site_id = create_resp.json()["id"]

        # Create config
        await db_client.put(
            f"/api/v1/sites/{site_id}/config",
            json={"blocking_mode": "opt_in"},
            headers=auth_headers,
        )

        # Patch config
        resp = await db_client.patch(
            f"/api/v1/sites/{site_id}/config",
            json={
                "blocking_mode": "opt_out",
                "gcm_enabled": False,
                "consent_expiry_days": 180,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocking_mode"] == "opt_out"
        assert data["gcm_enabled"] is False
        assert data["consent_expiry_days"] == 180

    async def test_reset_scalar_override_to_inherit(self, db_client, auth_headers):
        """PATCHing a scalar config field to null clears the override.

        Before migration 0009 the NOT NULL constraint rejected the
        update outright. With the column nullable, the row stores NULL
        and the editor endpoint returns the cascade-resolved value
        (system default in this test, since no org/group override is
        configured). The admin UI therefore always sees a concrete
        effective value; ``/inheritance`` is the source of truth for
        *which layer* supplied it.
        """
        domain = f"reset-{uuid.uuid4().hex[:8]}.com"
        create_resp = await db_client.post(
            "/api/v1/sites/",
            json={"domain": domain, "display_name": "Reset Test"},
            headers=auth_headers,
        )
        site_id = create_resp.json()["id"]
        await db_client.put(
            f"/api/v1/sites/{site_id}/config",
            json={"blocking_mode": "opt_out", "consent_expiry_days": 180},
            headers=auth_headers,
        )

        resp = await db_client.patch(
            f"/api/v1/sites/{site_id}/config",
            json={"blocking_mode": None, "consent_expiry_days": None},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        # PATCH response already reflects the cascade-resolved value.
        body = resp.json()
        assert body["blocking_mode"] == "opt_in"
        assert body["consent_expiry_days"] == 365

        # GET should agree with PATCH.
        get_resp = await db_client.get(
            f"/api/v1/sites/{site_id}/config",
            headers=auth_headers,
        )
        get_body = get_resp.json()
        assert get_body["blocking_mode"] == "opt_in"
        assert get_body["consent_expiry_days"] == 365

        # /inheritance is the source of truth for "where did this come
        # from?". After resetting, the source should drop back to system
        # since no org/group override is set in this test.
        inh = await db_client.get(
            f"/api/v1/config/sites/{site_id}/inheritance",
            headers=auth_headers,
        )
        fields = inh.json()["fields"]
        assert fields["blocking_mode"]["site_value"] is None
        assert fields["blocking_mode"]["source"] == "system"
        assert fields["blocking_mode"]["resolved_value"] == "opt_in"

    async def test_blank_url_is_coerced_to_inherit(self, db_client, auth_headers):
        """Submitting an empty string for a URL field clears the override.

        Without the ``coerce_blank_to_none`` validator the empty string
        would be persisted and the resolver's ``_merge_non_none`` would
        treat it as an explicit override, blocking inheritance. The
        system default for ``privacy_policy_url`` is None, so after the
        reset the editor sees a true None - the form renders empty and
        the inheritance endpoint reports the field as unset everywhere.
        """
        domain = f"blank-{uuid.uuid4().hex[:8]}.com"
        create_resp = await db_client.post(
            "/api/v1/sites/",
            json={"domain": domain, "display_name": "Blank Test"},
            headers=auth_headers,
        )
        site_id = create_resp.json()["id"]
        await db_client.put(
            f"/api/v1/sites/{site_id}/config",
            json={
                "blocking_mode": "opt_in",
                "privacy_policy_url": "https://example.com/privacy",
            },
            headers=auth_headers,
        )

        resp = await db_client.patch(
            f"/api/v1/sites/{site_id}/config",
            json={"privacy_policy_url": ""},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        # The empty string is coerced to NULL on the row and there is no
        # cascade source for privacy_policy_url, so the resolved value
        # is None too.
        assert resp.json()["privacy_policy_url"] is None

        inh = await db_client.get(
            f"/api/v1/config/sites/{site_id}/inheritance",
            headers=auth_headers,
        )
        url_info = inh.json()["fields"]["privacy_policy_url"]
        assert url_info["site_value"] is None
        assert url_info["resolved_value"] is None


@requires_db
class TestPublicCookies:
    async def test_returns_only_enabled_categories(self, db_client, auth_headers):
        domain = f"cookies-{uuid.uuid4().hex[:8]}.com"
        create_resp = await db_client.post(
            "/api/v1/sites/",
            json={"domain": domain, "display_name": "Cookies Test"},
            headers=auth_headers,
        )
        site_id = create_resp.json()["id"]
        await db_client.put(
            f"/api/v1/sites/{site_id}/config",
            json={
                "blocking_mode": "opt_in",
                "enabled_categories": ["necessary", "analytics"],
            },
            headers=auth_headers,
        )

        resp = await db_client.get(f"/api/v1/config/sites/{site_id}/cookies")
        assert resp.status_code == 200
        body = resp.json()
        slugs = [c["slug"] for c in body["categories"]]
        assert "necessary" in slugs
        assert "analytics" in slugs
        assert "marketing" not in slugs
        assert "functional" not in slugs

    async def test_returns_site_metadata(self, db_client, auth_headers):
        domain = f"meta-{uuid.uuid4().hex[:8]}.com"
        create_resp = await db_client.post(
            "/api/v1/sites/",
            json={"domain": domain, "display_name": "Meta Co"},
            headers=auth_headers,
        )
        site_id = create_resp.json()["id"]
        await db_client.put(
            f"/api/v1/sites/{site_id}/config",
            json={"blocking_mode": "opt_in", "consent_expiry_days": 180},
            headers=auth_headers,
        )

        resp = await db_client.get(f"/api/v1/config/sites/{site_id}/cookies")
        assert resp.status_code == 200
        body = resp.json()
        assert body["site_name"] == "Meta Co"
        assert body["domain"] == domain
        assert body["consent_expiry_days"] == 180

    async def test_returns_404_for_missing_site(self, db_client):
        missing = uuid.uuid4()
        resp = await db_client.get(f"/api/v1/config/sites/{missing}/cookies")
        assert resp.status_code == 404
