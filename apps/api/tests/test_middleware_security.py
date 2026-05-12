"""Tests for the security headers middleware."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestSecurityHeaders:
    @pytest.mark.asyncio
    async def test_x_content_type_options(self, client):
        resp = await client.get("/health")
        assert resp.headers["x-content-type-options"] == "nosniff"

    @pytest.mark.asyncio
    async def test_x_frame_options(self, client):
        resp = await client.get("/health")
        assert resp.headers["x-frame-options"] == "DENY"

    @pytest.mark.asyncio
    async def test_x_xss_protection(self, client):
        resp = await client.get("/health")
        assert resp.headers["x-xss-protection"] == "0"

    @pytest.mark.asyncio
    async def test_referrer_policy(self, client):
        resp = await client.get("/health")
        assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"

    @pytest.mark.asyncio
    async def test_content_security_policy(self, client):
        resp = await client.get("/health")
        assert resp.headers["content-security-policy"] == "default-src 'none'"

    @pytest.mark.asyncio
    async def test_no_hsts_on_http(self, client):
        resp = await client.get("/health")
        assert "strict-transport-security" not in resp.headers

    @pytest.mark.asyncio
    async def test_hsts_on_https(self, app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as client:
            resp = await client.get("/health")
        assert "strict-transport-security" in resp.headers
        assert "max-age=63072000" in resp.headers["strict-transport-security"]

    @pytest.mark.asyncio
    async def test_headers_present_on_non_existent_route(self, client):
        # Even 404s on unknown routes should have security headers
        resp = await client.get("/this-does-not-exist")
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "DENY"

    @pytest.mark.asyncio
    async def test_docs_gets_relaxed_csp(self, client):
        # Swagger UI needs to load its own JS/CSS from a CDN. The strict
        # ``default-src 'none'`` would otherwise refuse them and ``/docs``
        # would render as a blank page.
        resp = await client.get("/docs")
        csp = resp.headers["content-security-policy"]
        assert "default-src 'none'" not in csp
        assert "cdn.jsdelivr.net" in csp
        # X-Frame-Options is still set on docs — defence in depth.
        assert resp.headers["x-frame-options"] == "DENY"

    @pytest.mark.asyncio
    async def test_openapi_json_gets_relaxed_csp(self, client):
        # Swagger UI fetches the OpenAPI schema as JSON; that endpoint
        # needs the same carve-out so the fetch isn't blocked.
        resp = await client.get("/openapi.json")
        csp = resp.headers["content-security-policy"]
        assert "default-src 'none'" not in csp

    @pytest.mark.asyncio
    async def test_api_endpoints_still_get_strict_csp(self, client):
        # The CSP carve-out is narrow — every other path keeps the
        # strict default-src 'none'.
        resp = await client.get("/health")
        assert resp.headers["content-security-policy"] == "default-src 'none'"
