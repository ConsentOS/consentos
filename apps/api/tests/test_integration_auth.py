"""Integration tests for authentication endpoints (requires database)."""

from tests.conftest import requires_db


@requires_db
class TestAuthLogin:
    async def test_login_success(self, db_client, test_user):
        resp = await db_client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "TestPassword123",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, db_client, test_user):
        resp = await db_client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "wrong",
            },
        )
        assert resp.status_code == 401

    async def test_login_nonexistent_user(self, db_client):
        resp = await db_client.post(
            "/api/v1/auth/login",
            json={
                "email": "nobody@test.com",
                "password": "anything",
            },
        )
        assert resp.status_code == 401

    async def test_login_invalid_email(self, db_client):
        resp = await db_client.post(
            "/api/v1/auth/login",
            json={"email": "not-an-email", "password": "anything"},
        )
        assert resp.status_code == 422


@requires_db
class TestAuthMe:
    async def test_me_returns_user(self, db_client, auth_headers, test_user):
        resp = await db_client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == test_user.email
        assert data["role"] == "owner"
        assert data["is_superuser"] is False

    async def test_me_reports_platform_admin(self, db_client, superuser_headers):
        resp = await db_client.get("/api/v1/auth/me", headers=superuser_headers)
        assert resp.status_code == 200
        assert resp.json()["is_superuser"] is True

    async def test_profile_update_cannot_grant_platform_admin(self, db_client, auth_headers):
        resp = await db_client.patch(
            "/api/v1/auth/me",
            headers=auth_headers,
            json={"full_name": "Still An Owner", "is_superuser": True},
        )
        assert resp.status_code == 200
        assert resp.json()["is_superuser"] is False

    async def test_me_without_token(self, db_client):
        resp = await db_client.get("/api/v1/auth/me")
        assert resp.status_code == 401


@requires_db
class TestAuthRefresh:
    async def test_refresh_returns_new_tokens(self, db_client, test_user):
        # First login to get a refresh token
        login_resp = await db_client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "TestPassword123",
            },
        )
        refresh_token = login_resp.json()["refresh_token"]

        resp = await db_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_refresh_with_invalid_token(self, db_client):
        resp = await db_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid-token"},
        )
        assert resp.status_code == 401
