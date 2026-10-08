"""Integration tests for organisation scoping of sites and site groups."""

import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.site import Site
from src.routers.config import _get_site_group_id
from tests.conftest import create_test_site, requires_db


async def _create_group(client, headers) -> str:
    resp = await client.post(
        "/api/v1/site-groups/",
        json={"name": f"group-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@requires_db
class TestSiteGroupAssignment:
    async def test_create_with_own_group(self, db_client, auth_headers):
        group_id = await _create_group(db_client, auth_headers)
        resp = await db_client.post(
            "/api/v1/sites/",
            json={
                "domain": f"own-{uuid.uuid4().hex[:8]}.com",
                "display_name": "Own",
                "site_group_id": group_id,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["site_group_id"] == group_id

    async def test_create_with_other_org_group_rejected(
        self, db_client, auth_headers, other_org_headers
    ):
        other_group_id = await _create_group(db_client, other_org_headers)
        resp = await db_client.post(
            "/api/v1/sites/",
            json={
                "domain": f"foreign-{uuid.uuid4().hex[:8]}.com",
                "display_name": "Foreign",
                "site_group_id": other_group_id,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_create_with_unknown_group_rejected(self, db_client, auth_headers):
        resp = await db_client.post(
            "/api/v1/sites/",
            json={
                "domain": f"unknown-{uuid.uuid4().hex[:8]}.com",
                "display_name": "Unknown",
                "site_group_id": str(uuid.uuid4()),
            },
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_update_with_own_group(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        group_id = await _create_group(db_client, auth_headers)
        resp = await db_client.patch(
            f"/api/v1/sites/{site_id}",
            json={"site_group_id": group_id},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["site_group_id"] == group_id

    async def test_update_with_other_org_group_rejected(
        self, db_client, auth_headers, other_org_headers
    ):
        site_id = await create_test_site(db_client, auth_headers)
        other_group_id = await _create_group(db_client, other_org_headers)
        resp = await db_client.patch(
            f"/api/v1/sites/{site_id}",
            json={"site_group_id": other_group_id},
            headers=auth_headers,
        )
        assert resp.status_code == 404

        resp = await db_client.get(f"/api/v1/sites/{site_id}", headers=auth_headers)
        assert resp.json()["site_group_id"] is None

    async def test_update_clears_group(self, db_client, auth_headers):
        group_id = await _create_group(db_client, auth_headers)
        site_id = await create_test_site(db_client, auth_headers)
        await db_client.patch(
            f"/api/v1/sites/{site_id}",
            json={"site_group_id": group_id},
            headers=auth_headers,
        )
        resp = await db_client.patch(
            f"/api/v1/sites/{site_id}",
            json={"site_group_id": None},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["site_group_id"] is None


@requires_db
class TestSiteGroupLookup:
    async def test_returns_own_group(self, db_client, auth_headers, _test_engine):
        group_id = await _create_group(db_client, auth_headers)
        site_id = await create_test_site(db_client, auth_headers)
        await db_client.patch(
            f"/api/v1/sites/{site_id}",
            json={"site_group_id": group_id},
            headers=auth_headers,
        )
        async with AsyncSession(_test_engine) as session:
            assert await _get_site_group_id(uuid.UUID(site_id), session) == uuid.UUID(group_id)

    async def test_ignores_mismatched_group(
        self, db_client, auth_headers, other_org_headers, _test_engine
    ):
        site_id = await create_test_site(db_client, auth_headers)
        other_group_id = await _create_group(db_client, other_org_headers)
        async with AsyncSession(_test_engine) as session:
            await session.execute(
                update(Site)
                .where(Site.id == uuid.UUID(site_id))
                .values(site_group_id=uuid.UUID(other_group_id))
            )
            await session.commit()
            assert await _get_site_group_id(uuid.UUID(site_id), session) is None

    async def test_returns_none_without_group(self, db_client, auth_headers, _test_engine):
        site_id = await create_test_site(db_client, auth_headers)
        async with AsyncSession(_test_engine) as session:
            assert await _get_site_group_id(uuid.UUID(site_id), session) is None


@requires_db
class TestComplianceSiteScoping:
    async def test_own_site(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        resp = await db_client.post(f"/api/v1/compliance/check/{site_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["site_id"] == site_id

    async def test_other_org_site_not_found(self, db_client, auth_headers, other_org_headers):
        site_id = await create_test_site(db_client, other_org_headers)
        resp = await db_client.post(f"/api/v1/compliance/check/{site_id}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_deleted_site_not_found(self, db_client, auth_headers):
        site_id = await create_test_site(db_client, auth_headers)
        await db_client.delete(f"/api/v1/sites/{site_id}", headers=auth_headers)
        resp = await db_client.post(f"/api/v1/compliance/check/{site_id}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_unknown_site_not_found(self, db_client, auth_headers):
        resp = await db_client.post(
            f"/api/v1/compliance/check/{uuid.uuid4()}", headers=auth_headers
        )
        assert resp.status_code == 404
