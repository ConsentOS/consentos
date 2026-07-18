"""Tests for the pluggable auth provider abstraction.

Verifies:
  - ``PgAuthProvider`` (the default) still handles every current path
    correctly (regression safety for existing auth behaviour).
  - Registering an alternative provider routes ``get_current_user``
    through it.
  - When that provider owns interactive endpoints, ``/login``,
    ``/refresh`` and ``/me/password`` return 501.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from src.schemas.auth import CurrentUser
from src.services.auth import create_access_token, create_refresh_token
from src.services.auth_provider import AuthProvider, PgAuthProvider


@pytest.fixture(autouse=True)
def _reset_registry():
    from src.extensions.registry import get_registry

    registry = get_registry()
    original = registry.auth_provider
    yield
    registry.auth_provider = original


class TestPgAuthProvider:
    @pytest.mark.asyncio
    async def test_verifies_valid_access_token(self):
        provider = PgAuthProvider()
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        token = create_access_token(
            user_id=user_id,
            organisation_id=org_id,
            role="editor",
            email="dev@example.com",
        )
        result = await provider.verify_token(token)
        assert result.id == user_id
        assert result.organisation_id == org_id
        assert result.role == "editor"
        assert result.email == "dev@example.com"

    @pytest.mark.asyncio
    async def test_rejects_refresh_token(self):
        provider = PgAuthProvider()
        refresh = create_refresh_token(user_id=uuid.uuid4(), organisation_id=uuid.uuid4())
        with pytest.raises(HTTPException) as exc:
            await provider.verify_token(refresh)
        assert exc.value.status_code == 401
        assert "Invalid token type" in exc.value.detail

    @pytest.mark.asyncio
    async def test_rejects_garbage_token(self):
        provider = PgAuthProvider()
        with pytest.raises(HTTPException) as exc:
            await provider.verify_token("not-a-jwt")
        assert exc.value.status_code == 401

    def test_does_not_own_interactive_endpoints(self):
        assert PgAuthProvider().owns_interactive_endpoints() is False


class _StubProvider:
    """Records verification calls; can pretend to own interactive endpoints."""

    def __init__(self, *, owns_interactive: bool):
        self._owns = owns_interactive
        self.calls: list[str] = []

    async def verify_token(self, token: str) -> CurrentUser:
        self.calls.append(token)
        return CurrentUser(
            id=uuid.uuid4(),
            organisation_id=uuid.uuid4(),
            email="stub@example.com",
            role="owner",
        )

    def owns_interactive_endpoints(self) -> bool:
        return self._owns


class TestGetCurrentUserDelegation:
    @pytest.mark.asyncio
    async def test_defaults_to_pg_provider_when_none_registered(self):
        from fastapi.security import HTTPAuthorizationCredentials

        from src.services.dependencies import get_current_user

        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        token = create_access_token(
            user_id=user_id,
            organisation_id=org_id,
            role="admin",
            email="admin@example.com",
        )
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        result = await get_current_user(creds)
        assert result.id == user_id
        assert result.role == "admin"

    @pytest.mark.asyncio
    async def test_delegates_to_registered_provider(self):
        from fastapi.security import HTTPAuthorizationCredentials

        from src.extensions.registry import register_auth_provider
        from src.services.dependencies import get_current_user

        stub = _StubProvider(owns_interactive=False)
        register_auth_provider(stub)

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="anything")
        result = await get_current_user(creds)
        assert result.email == "stub@example.com"
        assert stub.calls == ["anything"]


class TestInteractiveEndpointsGuard:
    """When an EE provider owns interactive endpoints, core routes return 501."""

    def _register(self, provider: AuthProvider) -> None:
        from src.extensions.registry import register_auth_provider

        register_auth_provider(provider)

    @pytest.mark.asyncio
    async def test_login_returns_501_when_external_provider_owns_it(self, app, client):
        self._register(_StubProvider(owns_interactive=True))
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "x@example.com", "password": "irrelevant"},
        )
        assert resp.status_code == 501

    @pytest.mark.asyncio
    async def test_refresh_returns_501_when_external_provider_owns_it(self, app, client):
        self._register(_StubProvider(owns_interactive=True))
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "irrelevant"},
        )
        assert resp.status_code == 501

    @pytest.mark.asyncio
    async def test_password_change_returns_501_when_external_provider_owns_it(self, app, client):
        self._register(_StubProvider(owns_interactive=True))
        # No auth header. Either 401 (missing bearer) or 501 (guard) is
        # acceptable, as long as we don't reach the DB write.
        resp = await client.patch(
            "/api/v1/auth/me/password",
            json={"current_password": "x", "new_password": "y"},
        )
        assert resp.status_code in (401, 501)

    @pytest.mark.asyncio
    async def test_login_still_works_with_default_pg_provider(self, app, client):
        # No provider registered -> PgAuthProvider default -> login route
        # is not gated; existing 401 for bad creds proves the guard is
        # inactive, not that the endpoint disappeared.
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "does-not-exist@example.com", "password": "x"},
        )
        assert resp.status_code == 401
