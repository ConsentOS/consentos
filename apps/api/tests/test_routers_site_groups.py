"""Unit tests for site-groups router — mocked database."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import create_app
from src.services.auth import create_access_token

ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _auth_headers():
    token = create_access_token(
        user_id=USER_ID, organisation_id=ORG_ID, role="owner", email="admin@test.com"
    )
    return {"Authorization": f"Bearer {token}"}


def _mock_group(**overrides):
    group = MagicMock()
    group.id = overrides.get("id", uuid.uuid4())
    group.organisation_id = overrides.get("organisation_id", ORG_ID)
    group.name = overrides.get("name", "EU Storefront")
    group.description = overrides.get("description")
    group.deleted_at = None
    group.created_at = datetime.now(UTC)
    group.updated_at = datetime.now(UTC)
    return group


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
        if isinstance(r, list):
            result.scalar_one_or_none.return_value = r[0] if r else None
            result.scalar_one.return_value = len(r) if isinstance(r[0], int) else 0
            scalars_obj = MagicMock()
            scalars_obj.all.return_value = r
            result.scalars.return_value = scalars_obj
            result.all.return_value = r
        elif isinstance(r, int):
            result.scalar_one.return_value = r
            result.scalar_one_or_none.return_value = r
        elif isinstance(r, tuple):
            # (group, site_count) rows for list endpoint
            result.all.return_value = r
        else:
            result.scalar_one_or_none.return_value = r
            result.scalar_one.return_value = r if r is not None else 0
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


class TestSiteGroupCRUD:
    @pytest.mark.asyncio
    async def test_create_site_group(self, mock_app):
        """POST /site-groups/ creates a new group."""
        db = _mock_db_sequence(None)  # no duplicate
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/site-groups/",
                json={"name": "EU Storefront"},
                headers=_auth_headers(),
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "EU Storefront"
        assert data["site_count"] == 0

    @pytest.mark.asyncio
    async def test_create_site_group_conflict(self, mock_app):
        """POST /site-groups/ returns 409 when name exists."""
        existing = _mock_group(name="EU Storefront")
        db = _mock_db_sequence(existing)
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/site-groups/",
                json={"name": "EU Storefront"},
                headers=_auth_headers(),
            )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_list_site_groups(self, mock_app):
        """GET /site-groups/ returns groups with site counts."""
        group = _mock_group(name="EU Storefront")
        row = MagicMock()
        row.SiteGroup = group
        row.site_count = 3
        rows = (row,)
        db = _mock_db_sequence(rows)
        async with await _client(mock_app, db) as client:
            resp = await client.get(
                "/api/v1/site-groups/",
                headers=_auth_headers(),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "EU Storefront"
        assert data[0]["site_count"] == 3

    @pytest.mark.asyncio
    async def test_get_site_group(self, mock_app):
        """GET /site-groups/{id} returns a single group."""
        group_id = uuid.uuid4()
        group = _mock_group(id=group_id, description="EU regional sites")
        db = _mock_db_sequence(group, 2)  # group lookup, site count
        async with await _client(mock_app, db) as client:
            resp = await client.get(
                f"/api/v1/site-groups/{group_id}",
                headers=_auth_headers(),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "EU regional sites"
        assert data["site_count"] == 2

    @pytest.mark.asyncio
    async def test_get_site_group_not_found(self, mock_app):
        """GET /site-groups/{id} returns 404 for unknown ID."""
        db = _mock_db_sequence(None)
        async with await _client(mock_app, db) as client:
            resp = await client.get(
                f"/api/v1/site-groups/{uuid.uuid4()}",
                headers=_auth_headers(),
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_site_group(self, mock_app):
        """DELETE /site-groups/{id} soft-deletes and ungroups sites."""
        group_id = uuid.uuid4()
        group = _mock_group(id=group_id)
        site = MagicMock()
        site.site_group_id = group_id
        db = _mock_db_sequence(group, [site])  # group lookup, sites in group
        async with await _client(mock_app, db) as client:
            resp = await client.delete(
                f"/api/v1/site-groups/{group_id}",
                headers=_auth_headers(),
            )
        assert resp.status_code == 204
        assert site.site_group_id is None
        assert group.deleted_at is not None
