"""Integration tests for the dynamic CORS middleware (requires database)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services import cors as cors_module
from tests.conftest import requires_db


@pytest.fixture(autouse=True)
def _cors_isolated_from_global_state(_test_engine, monkeypatch):
    """Pin the middleware to the test engine and disable Redis.

    Avoids binding the global engine to the session loop (which would leak
    into function-loop tests) and exercises the DB-fallback path; the Redis
    logic is covered by test_cors.py.
    """

    async def _fetch_via_test_engine() -> set[str]:
        async with AsyncSession(_test_engine, expire_on_commit=False) as db:
            return await cors_module.get_allowed_domains(db)

    monkeypatch.setattr(cors_module, "_fetch_allowed_domains", _fetch_via_test_engine)
    monkeypatch.setattr(cors_module, "_get_redis", lambda: None)


def _origin_for(prefix: str) -> tuple[str, str]:
    """Return a (domain, origin) pair unique enough to avoid collisions."""
    domain = f"{prefix}-{uuid.uuid4().hex[:8]}.test"
    return domain, f"https://{domain}"


async def _create_site(client, headers, domain: str) -> None:
    resp = await client.post(
        "/api/v1/sites/",
        json={"domain": domain, "display_name": "CORS test site"},
        headers=headers,
    )
    assert resp.status_code == 201, f"Failed to create site: {resp.text}"


@requires_db
class TestDynamicCorsMiddleware:
    async def test_registered_site_origin_is_allowed(self, db_client, auth_headers):
        domain, origin = _origin_for("shop")
        await _create_site(db_client, auth_headers, domain)

        resp = await db_client.get(
            "/api/v1/sites/",
            headers={**auth_headers, "Origin": origin},
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == origin
        assert resp.headers["access-control-allow-credentials"] == "true"
        assert "origin" in resp.headers["vary"].lower()

    async def test_additional_domain_is_allowed(self, db_client, auth_headers):
        domain, _ = _origin_for("primary")
        extra = f"extra-{uuid.uuid4().hex[:8]}.test"
        extra_origin = f"https://{extra}"

        create = await db_client.post(
            "/api/v1/sites/",
            json={"domain": domain, "display_name": "Multi-domain"},
            headers=auth_headers,
        )
        site_id = create.json()["id"]

        patch = await db_client.patch(
            f"/api/v1/sites/{site_id}",
            json={"additional_domains": [extra]},
            headers=auth_headers,
        )
        assert patch.status_code == 200
        assert patch.json()["additional_domains"] == [extra]

        resp = await db_client.get(
            "/api/v1/sites/",
            headers={**auth_headers, "Origin": extra_origin},
        )
        assert resp.headers["access-control-allow-origin"] == extra_origin

    async def test_unregistered_origin_gets_no_allow_header(self, db_client, auth_headers):
        resp = await db_client.get(
            "/api/v1/sites/",
            headers={**auth_headers, "Origin": "https://evil.test"},
        )
        assert "access-control-allow-origin" not in resp.headers

    async def test_subdomain_not_implicitly_allowed(self, db_client, auth_headers):
        domain, _ = _origin_for("apex")
        await _create_site(db_client, auth_headers, domain)

        resp = await db_client.get(
            "/api/v1/sites/",
            headers={**auth_headers, "Origin": f"https://evil.{domain}"},
        )
        assert "access-control-allow-origin" not in resp.headers

    async def test_static_origin_still_allowed(self, db_client, auth_headers):
        resp = await db_client.get(
            "/api/v1/sites/",
            headers={**auth_headers, "Origin": "http://localhost:5173"},
        )
        assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"

    async def test_preflight_registered_origin_ok(self, db_client, auth_headers):
        domain, origin = _origin_for("preflight")
        await _create_site(db_client, auth_headers, domain)

        resp = await db_client.options(
            "/api/v1/sites/",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == origin
        assert resp.headers["access-control-allow-credentials"] == "true"
        assert resp.headers["access-control-allow-methods"]
        assert resp.headers["access-control-allow-headers"] == "content-type"

    async def test_preflight_unregistered_origin_rejected(self, db_client):
        resp = await db_client.options(
            "/api/v1/sites/",
            headers={
                "Origin": "https://evil.test",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 400
        assert "access-control-allow-origin" not in resp.headers
