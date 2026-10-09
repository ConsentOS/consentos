"""Unit tests for organisation and user routers — mocked database."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import create_app
from src.services.auth import create_access_token, hash_password

ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _auth_headers(role="owner"):
    token = create_access_token(
        user_id=USER_ID, organisation_id=ORG_ID, role=role, email="admin@test.com"
    )
    return {"Authorization": f"Bearer {token}"}


def _mock_org(**overrides):
    org = MagicMock(spec=[])
    org.id = overrides.get("id", ORG_ID)
    org.name = overrides.get("name", "Test Org")
    org.slug = overrides.get("slug", "test-org")
    org.contact_email = overrides.get("contact_email")
    org.deleted_at = None
    org.created_at = datetime.now(UTC)
    org.updated_at = datetime.now(UTC)
    return org


def _mock_user(**overrides):
    user = MagicMock(spec=[])
    user.id = overrides.get("id", uuid.uuid4())
    user.organisation_id = overrides.get("organisation_id", ORG_ID)
    user.email = overrides.get("email", "user@test.com")
    user.password_hash = overrides.get("password_hash", hash_password("Pass123"))
    user.full_name = overrides.get("full_name", "Test User")
    user.role = overrides.get("role", "editor")
    user.is_active = True
    user.deleted_at = None
    user.created_at = datetime.now(UTC)
    user.updated_at = datetime.now(UTC)
    return user


def _mock_db_sequence(*results):
    session = AsyncMock()
    mock_results = []
    for r in results:
        result = MagicMock()
        if isinstance(r, list):
            result.scalar_one_or_none.return_value = r[0] if r else None
            scalars_obj = MagicMock()
            scalars_obj.all.return_value = r
            result.scalars.return_value = scalars_obj
        else:
            result.scalar_one_or_none.return_value = r
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
            if hasattr(obj, "is_active") and getattr(obj, "is_active", None) is None:
                obj.is_active = True
            if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.now(UTC)
            if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
                obj.updated_at = datetime.now(UTC)

    session.flush = AsyncMock(side_effect=_fake_flush)
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
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


_BOOTSTRAP_TOKEN = "test-bootstrap-token-xyz"
_BOOTSTRAP_HEADERS = {"X-Admin-Bootstrap-Token": _BOOTSTRAP_TOKEN}


@pytest.fixture
def _bootstrap_enabled(monkeypatch):
    """Configure the bootstrap token so org creation is permitted."""
    from src.config import settings as settings_mod

    monkeypatch.setattr(
        settings_mod.get_settings(),
        "admin_bootstrap_token",
        _BOOTSTRAP_TOKEN,
    )
    yield


class TestOrganisationRouter:
    @pytest.mark.asyncio
    async def test_create_org(self, mock_app, _bootstrap_enabled):
        db = _mock_db_sequence(None)  # no duplicate slug
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/organisations/",
                json={"name": "New Org", "slug": "new-org"},
                headers=_BOOTSTRAP_HEADERS,
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_org_duplicate_slug(self, mock_app, _bootstrap_enabled):
        existing = _mock_org(slug="dup-slug")
        db = _mock_db_sequence(existing)
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/organisations/",
                json={"name": "Another", "slug": "dup-slug"},
                headers=_BOOTSTRAP_HEADERS,
            )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_create_org_disabled_without_token(self, mock_app):
        """With no ``admin_bootstrap_token`` configured, creation is forbidden."""
        db = _mock_db_sequence(None)
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/organisations/",
                json={"name": "X", "slug": "x"},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_org_wrong_token(self, mock_app, _bootstrap_enabled):
        """With an incorrect token, creation is unauthorised."""
        db = _mock_db_sequence(None)
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/organisations/",
                json={"name": "X", "slug": "x"},
                headers={"X-Admin-Bootstrap-Token": "wrong"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_my_org(self, mock_app):
        org = _mock_org()
        db = _mock_db_sequence(org)
        async with await _client(mock_app, db) as client:
            resp = await client.get("/api/v1/organisations/me", headers=_auth_headers())
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_my_org_not_found(self, mock_app):
        db = _mock_db_sequence(None)
        async with await _client(mock_app, db) as client:
            resp = await client.get("/api/v1/organisations/me", headers=_auth_headers())
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_my_org(self, mock_app):
        org = _mock_org()
        db = _mock_db_sequence(org)
        async with await _client(mock_app, db) as client:
            resp = await client.patch(
                "/api/v1/organisations/me",
                json={"name": "Updated Name"},
                headers=_auth_headers(),
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_my_org_not_found(self, mock_app):
        db = _mock_db_sequence(None)
        async with await _client(mock_app, db) as client:
            resp = await client.patch(
                "/api/v1/organisations/me",
                json={"name": "Updated"},
                headers=_auth_headers(),
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_my_org_requires_admin(self, mock_app):
        db = _mock_db_sequence()
        async with await _client(mock_app, db) as client:
            resp = await client.patch(
                "/api/v1/organisations/me",
                json={"name": "Updated"},
                headers=_auth_headers(role="viewer"),
            )
        assert resp.status_code == 403


class TestUserRouter:
    @pytest.mark.asyncio
    async def test_create_user(self, mock_app):
        db = _mock_db_sequence(None)  # no duplicate email
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/users/",
                json={
                    "email": "new@test.com",
                    "password": "SecurePass123",
                    "full_name": "New User",
                    "role": "editor",
                },
                headers=_auth_headers(),
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email(self, mock_app):
        existing = _mock_user(email="dup@test.com")
        db = _mock_db_sequence(existing)
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/users/",
                json={
                    "email": "dup@test.com",
                    "password": "SecurePass123",
                    "full_name": "Dup User",
                    "role": "viewer",
                },
                headers=_auth_headers(),
            )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_list_users(self, mock_app):
        users = [_mock_user(), _mock_user(email="two@test.com")]
        db = _mock_db_sequence(users)
        async with await _client(mock_app, db) as client:
            resp = await client.get("/api/v1/users/", headers=_auth_headers())
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_user(self, mock_app):
        user = _mock_user()
        db = _mock_db_sequence(user)
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/users/{user.id}", headers=_auth_headers())
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, mock_app):
        db = _mock_db_sequence(None)
        async with await _client(mock_app, db) as client:
            resp = await client.get(f"/api/v1/users/{uuid.uuid4()}", headers=_auth_headers())
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_user(self, mock_app):
        user = _mock_user()
        db = _mock_db_sequence(user)
        async with await _client(mock_app, db) as client:
            resp = await client.patch(
                f"/api/v1/users/{user.id}",
                json={"full_name": "Updated Name", "role": "admin"},
                headers=_auth_headers(),
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_user_not_found(self, mock_app):
        db = _mock_db_sequence(None)
        async with await _client(mock_app, db) as client:
            resp = await client.patch(
                f"/api/v1/users/{uuid.uuid4()}",
                json={"full_name": "Nope"},
                headers=_auth_headers(),
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_user(self, mock_app):
        user = _mock_user(id=uuid.uuid4())
        db = _mock_db_sequence(user)
        async with await _client(mock_app, db) as client:
            resp = await client.delete(f"/api/v1/users/{user.id}", headers=_auth_headers())
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_self_rejected(self, mock_app):
        db = _mock_db_sequence()
        async with await _client(mock_app, db) as client:
            resp = await client.delete(f"/api/v1/users/{USER_ID}", headers=_auth_headers())
        assert resp.status_code == 400
        assert "yourself" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_user_not_found(self, mock_app):
        db = _mock_db_sequence(None)
        async with await _client(mock_app, db) as client:
            resp = await client.delete(f"/api/v1/users/{uuid.uuid4()}", headers=_auth_headers())
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_users_require_auth(self, mock_app):
        db = _mock_db_sequence()
        async with await _client(mock_app, db) as client:
            resp = await client.get("/api/v1/users/")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_create_user_viewer_forbidden(self, mock_app):
        db = _mock_db_sequence()
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/users/",
                json={
                    "email": "new@test.com",
                    "password": "SecurePass123",
                    "role": "viewer",
                },
                headers=_auth_headers(role="viewer"),
            )
        assert resp.status_code == 403
