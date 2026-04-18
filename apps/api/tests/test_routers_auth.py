"""Unit tests for auth router — mocked database."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import create_app
from src.services.auth import create_access_token, create_refresh_token, hash_password


def _make_user(org_id: uuid.UUID | None = None, **overrides):
    """Build a mock User ORM object."""
    _org_id = org_id or uuid.uuid4()
    _id = overrides.pop("id", uuid.uuid4())
    user = MagicMock()
    user.id = _id
    user.organisation_id = _org_id
    user.email = overrides.get("email", "admin@test.com")
    user.password_hash = overrides.get("password_hash", hash_password("TestPassword123"))
    user.full_name = overrides.get("full_name", "Test Admin")
    user.role = overrides.get("role", "owner")
    user.deleted_at = None
    user.is_active = True
    return user


def _mock_db(scalars=None, scalar_one_or_none=None):
    """Create a mock AsyncSession.

    When a query is executed:
      - result.scalar_one_or_none() returns `scalar_one_or_none`
      - result.scalars().all() returns `scalars or []`
    """
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    scalars_obj = MagicMock()
    scalars_obj.all.return_value = scalars or []
    result.scalars.return_value = scalars_obj
    session.execute.return_value = result
    return session


@pytest.fixture
def mock_app():
    return create_app()


async def _client(app, mock_session):
    """Build a test client with the given mock session."""
    from src.db import get_db

    async def _override():
        yield mock_session

    app.dependency_overrides[get_db] = _override
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestLoginEndpoint:
    @pytest.mark.asyncio
    async def test_login_success(self, mock_app):
        org_id = uuid.uuid4()
        user = _make_user(org_id=org_id)
        db = _mock_db(scalar_one_or_none=user)
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": "admin@test.com", "password": "TestPassword123"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, mock_app):
        user = _make_user()
        db = _mock_db(scalar_one_or_none=user)
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": "admin@test.com", "password": "WrongPassword"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_user_not_found(self, mock_app):
        db = _mock_db(scalar_one_or_none=None)
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": "nobody@test.com", "password": "whatever"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_invalid_body(self, mock_app):
        db = _mock_db()
        async with await _client(mock_app, db) as client:
            resp = await client.post("/api/v1/auth/login", json={"email": "not-an-email"})
        assert resp.status_code == 422


class TestMeEndpoint:
    @pytest.mark.asyncio
    async def test_me_returns_user(self, mock_app):
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        token = create_access_token(
            user_id=user_id,
            organisation_id=org_id,
            role="owner",
            email="admin@test.com",
        )
        mock_user = _make_user(id=user_id, org_id=org_id, email="admin@test.com", role="owner")
        db = _mock_db(scalar_one_or_none=mock_user)
        async with await _client(mock_app, db) as client:
            resp = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "admin@test.com"
        assert data["role"] == "owner"

    @pytest.mark.asyncio
    async def test_me_without_token(self, mock_app):
        db = _mock_db()
        async with await _client(mock_app, db) as client:
            resp = await client.get("/api/v1/auth/me")
        assert resp.status_code in (401, 403)


class TestRefreshEndpoint:
    @pytest.mark.asyncio
    async def test_refresh_success(self, mock_app):
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        user = _make_user(org_id=org_id, id=user_id)
        refresh_token = create_refresh_token(
            user_id=user_id,
            organisation_id=org_id,
        )
        db = _mock_db(scalar_one_or_none=user)
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_token},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data

    @pytest.mark.asyncio
    async def test_refresh_with_access_token_rejected(self, mock_app):
        """An access token should not be usable as a refresh token."""
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        access_token = create_access_token(
            user_id=user_id,
            organisation_id=org_id,
            role="owner",
            email="admin@test.com",
        )
        db = _mock_db()
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": access_token},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, mock_app):
        db = _mock_db()
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "invalid.token.here"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_user_deleted(self, mock_app):
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        refresh_token = create_refresh_token(
            user_id=user_id,
            organisation_id=org_id,
        )
        db = _mock_db(scalar_one_or_none=None)
        async with await _client(mock_app, db) as client:
            resp = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_token},
            )
        assert resp.status_code == 401
        assert "no longer exists" in resp.json()["detail"]
