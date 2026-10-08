"""Integration tests for consent recording endpoints (requires database)."""

import uuid

from tests.conftest import create_test_site, requires_db


@requires_db
class TestConsentEndpoints:
    async def test_record_consent(self, db_client, auth_headers):
        """POST /consent/ is public (no auth) — used by the banner."""
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="consent")
        resp = await db_client.post(
            "/api/v1/consent/",
            json={
                "site_id": site_id,
                "visitor_id": str(uuid.uuid4()),
                "action": "accept_all",
                "categories_accepted": [
                    "necessary",
                    "functional",
                    "analytics",
                    "marketing",
                    "personalisation",
                ],
                "categories_rejected": [],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["action"] == "accept_all"
        assert "id" in data

    async def test_record_consent_reject_all(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="consent-rej")
        resp = await db_client.post(
            "/api/v1/consent/",
            json={
                "site_id": site_id,
                "visitor_id": str(uuid.uuid4()),
                "action": "reject_all",
                "categories_accepted": ["necessary"],
                "categories_rejected": [
                    "functional",
                    "analytics",
                    "marketing",
                    "personalisation",
                ],
            },
        )
        assert resp.status_code == 201
        assert resp.json()["action"] == "reject_all"

    async def test_record_consent_custom(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="consent-cust")
        resp = await db_client.post(
            "/api/v1/consent/",
            json={
                "site_id": site_id,
                "visitor_id": str(uuid.uuid4()),
                "action": "custom",
                "categories_accepted": [
                    "necessary",
                    "analytics",
                ],
                "categories_rejected": [
                    "functional",
                    "marketing",
                    "personalisation",
                ],
            },
        )
        assert resp.status_code == 201
        assert resp.json()["action"] == "custom"

    async def test_get_consent_record(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="consent-get")
        # Create a consent record
        create_resp = await db_client.post(
            "/api/v1/consent/",
            json={
                "site_id": site_id,
                "visitor_id": str(uuid.uuid4()),
                "action": "accept_all",
                "categories_accepted": ["necessary"],
                "categories_rejected": [],
            },
        )
        consent_id = create_resp.json()["id"]

        resp = await db_client.get(
            f"/api/v1/consent/{consent_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == consent_id

    async def test_get_consent_requires_auth(self, db_client):
        """Reading a consent record without auth must be rejected."""
        resp = await db_client.get(f"/api/v1/consent/{uuid.uuid4()}")
        assert resp.status_code == 401

    async def test_verify_consent(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="consent-ver")
        create_resp = await db_client.post(
            "/api/v1/consent/",
            json={
                "site_id": site_id,
                "visitor_id": str(uuid.uuid4()),
                "action": "accept_all",
                "categories_accepted": ["necessary"],
                "categories_rejected": [],
            },
        )
        consent_id = create_resp.json()["id"]

        resp = await db_client.get(
            f"/api/v1/consent/verify/{consent_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert str(data["id"]) == consent_id

    async def test_get_consent_not_found(self, db_client, auth_headers):
        resp = await db_client.get(
            f"/api/v1/consent/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_verify_consent_not_found(self, db_client, auth_headers):
        resp = await db_client.get(
            f"/api/v1/consent/verify/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_record_consent_invalid_action(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers, domain_prefix="consent-inv")
        resp = await db_client.post(
            "/api/v1/consent/",
            json={
                "site_id": site_id,
                "visitor_id": str(uuid.uuid4()),
                "action": "invalid_action",
                "categories_accepted": ["necessary"],
                "categories_rejected": [],
            },
        )
        assert resp.status_code == 422

    async def test_record_consent_unknown_site_returns_404(self, db_client):
        resp = await db_client.post("/api/v1/consent/", json=_consent_body(str(uuid.uuid4())))
        assert resp.status_code == 404

    async def test_record_consent_inactive_site_returns_404(self, db_client, auth_headers):
        site_id, _ = await _create_site_with_domains(db_client, auth_headers)
        resp = await db_client.patch(
            f"/api/v1/sites/{site_id}", json={"is_active": False}, headers=auth_headers
        )
        assert resp.status_code == 200
        resp = await db_client.post("/api/v1/consent/", json=_consent_body(site_id))
        assert resp.status_code == 404

    async def test_record_consent_checks_origin(self, db_client, auth_headers):
        site_id, domain = await _create_site_with_domains(db_client, auth_headers)
        cases = [
            ({"origin": f"https://{domain}"}, 201),
            ({"origin": f"https://www.{domain}"}, 201),
            ({"referer": f"https://shop.alt-{domain}/basket"}, 201),
            ({}, 201),
            ({"origin": "https://elsewhere.test"}, 403),
            ({"referer": f"https://{domain}.elsewhere.test/"}, 403),
            ({"origin": "http://test"}, 201),
            ({"referer": "http://test/c/hosted/cookies"}, 201),
        ]
        for headers, expected in cases:
            resp = await db_client.post(
                "/api/v1/consent/", headers=headers, json=_consent_body(site_id)
            )
            assert resp.status_code == expected, headers


def _consent_body(site_id: str) -> dict:
    return {
        "site_id": site_id,
        "visitor_id": str(uuid.uuid4()),
        "action": "accept_all",
        "categories_accepted": ["necessary"],
        "categories_rejected": [],
    }


async def _create_site_with_domains(client, headers) -> tuple[str, str]:
    """Create a site with one additional domain and return its ID and primary domain."""
    domain = f"consent-origin-{uuid.uuid4().hex[:8]}.com"
    resp = await client.post(
        "/api/v1/sites/",
        json={"domain": domain, "display_name": "Origin Test"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    site_id = resp.json()["id"]
    resp = await client.patch(
        f"/api/v1/sites/{site_id}",
        json={"additional_domains": [f"alt-{domain}"]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return site_id, domain
