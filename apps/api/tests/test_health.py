import pytest


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["edition"] in ("ce", "ee")


@pytest.mark.asyncio
async def test_openapi_schema(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "ConsentOS API"
    # Version is injected at build time; source/test builds use the sentinel.
    assert schema["info"]["version"] == "0.0.0-dev"


@pytest.mark.asyncio
async def test_api_routes_registered(client):
    response = await client.get("/openapi.json")
    paths = response.json()["paths"]
    assert "/health" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/config/sites/{site_id}" in paths
    assert "/api/v1/consent/" in paths
    assert "/api/v1/scanner/scans" in paths
    assert "/api/v1/compliance/check/{site_id}" in paths
