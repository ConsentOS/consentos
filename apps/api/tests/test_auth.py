"""Tests for JWT authentication service and dependencies."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from jose import JWTError, jwt

from src.config.settings import get_settings
from src.schemas.auth import CurrentUser
from src.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        password = "s3cureP@ss!"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("correct")
        assert not verify_password("wrong", hashed)

    def test_different_hashes_for_same_password(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # bcrypt salts differ


class TestJWTTokens:
    @pytest.fixture
    def user_data(self):
        return {
            "user_id": uuid.uuid4(),
            "organisation_id": uuid.uuid4(),
            "role": "admin",
            "email": "test@example.com",
        }

    def test_create_access_token_decodable(self, user_data):
        token = create_access_token(**user_data)
        payload = decode_token(token)
        assert payload["sub"] == str(user_data["user_id"])
        assert payload["org_id"] == str(user_data["organisation_id"])
        assert payload["role"] == "admin"
        assert payload["email"] == "test@example.com"
        assert payload["type"] == "access"

    def test_create_refresh_token_decodable(self, user_data):
        token = create_refresh_token(
            user_id=user_data["user_id"],
            organisation_id=user_data["organisation_id"],
        )
        payload = decode_token(token)
        assert payload["sub"] == str(user_data["user_id"])
        assert payload["type"] == "refresh"

    def test_access_token_expiry(self, user_data):
        token = create_access_token(**user_data)
        payload = decode_token(token)
        settings = get_settings()
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        iat = datetime.fromtimestamp(payload["iat"], tz=UTC)
        delta = exp - iat
        assert abs(delta.total_seconds() - settings.jwt_access_token_expire_minutes * 60) < 5

    def test_refresh_token_expiry(self, user_data):
        token = create_refresh_token(
            user_id=user_data["user_id"],
            organisation_id=user_data["organisation_id"],
        )
        payload = decode_token(token)
        settings = get_settings()
        exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
        iat = datetime.fromtimestamp(payload["iat"], tz=UTC)
        delta = exp - iat
        expected = settings.jwt_refresh_token_expire_days * 86400
        assert abs(delta.total_seconds() - expected) < 5

    def test_expired_token_raises(self):
        settings = get_settings()
        payload = {
            "sub": str(uuid.uuid4()),
            "org_id": str(uuid.uuid4()),
            "role": "viewer",
            "exp": datetime.now(UTC) - timedelta(hours=1),
            "iat": datetime.now(UTC) - timedelta(hours=2),
            "type": "access",
        }
        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        with pytest.raises(JWTError):
            decode_token(token)

    def test_tampered_token_raises(self, user_data):
        token = create_access_token(**user_data)
        # Tamper with the token
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(JWTError):
            decode_token(tampered)


class TestCurrentUser:
    def test_has_role(self):
        user = CurrentUser(
            id=uuid.uuid4(),
            organisation_id=uuid.uuid4(),
            email="admin@example.com",
            role="admin",
        )
        assert user.has_role("admin", "owner")
        assert not user.has_role("editor", "viewer")

    def test_is_admin(self):
        admin = CurrentUser(
            id=uuid.uuid4(),
            organisation_id=uuid.uuid4(),
            email="a@b.com",
            role="admin",
        )
        viewer = CurrentUser(
            id=uuid.uuid4(),
            organisation_id=uuid.uuid4(),
            email="v@b.com",
            role="viewer",
        )
        assert admin.is_admin
        assert not viewer.is_admin


@pytest.mark.asyncio
class TestAuthEndpoints:
    async def test_me_without_token_returns_401(self, client):
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401

    async def test_me_with_valid_token(self, app):
        from unittest.mock import AsyncMock, MagicMock

        from src.db import get_db

        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        token = create_access_token(
            user_id=user_id,
            organisation_id=org_id,
            role="editor",
            email="user@example.com",
        )

        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.organisation_id = org_id
        mock_user.email = "user@example.com"
        mock_user.full_name = "Test User"
        mock_user.role = "editor"
        mock_user.deleted_at = None

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute.return_value = mock_result

        async def _override():
            yield mock_session

        app.dependency_overrides[get_db] = _override

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )

        app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(user_id)
        assert data["organisation_id"] == str(org_id)
        assert data["role"] == "editor"
        assert data["email"] == "user@example.com"

    async def test_me_with_refresh_token_rejected(self, client):
        token = create_refresh_token(
            user_id=uuid.uuid4(),
            organisation_id=uuid.uuid4(),
        )
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    async def test_me_with_invalid_token(self, client):
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert response.status_code == 401
