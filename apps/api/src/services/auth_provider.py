"""Pluggable authentication provider abstraction.

Core ships ``PgAuthProvider`` which verifies JWTs issued by ConsentOS
against the local users table. Enterprise extensions can register an
alternative provider (e.g. Clerk, Keycloak, FusionAuth) via
``extensions.registry.register_auth_provider`` to delegate authentication
to a hosted or self-hosted IdP.

A provider that owns interactive endpoints (login, refresh, register,
password change) also disables the core ``/api/v1/auth/*`` routes for
those operations, since the IdP handles them itself.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from fastapi import HTTPException, status
from jose import JWTError

from src.schemas.auth import CurrentUser
from src.services.auth import decode_token


@runtime_checkable
class AuthProvider(Protocol):
    """Verifies a bearer token and maps it to a ``CurrentUser``."""

    async def verify_token(self, token: str) -> CurrentUser:
        """Return the user for a valid token; raise HTTPException 401 otherwise."""
        ...

    def owns_interactive_endpoints(self) -> bool:
        """Whether this provider owns login / refresh / register / password change.

        When True, the core auth router disables those routes and expects
        the provider (typically an external IdP) to handle them.
        """
        ...


class PgAuthProvider:
    """Default provider: verifies JWTs issued by ConsentOS."""

    async def verify_token(self, token: str) -> CurrentUser:
        try:
            payload = decode_token(token)
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        return CurrentUser(
            id=uuid.UUID(payload["sub"]),
            organisation_id=uuid.UUID(payload["org_id"]),
            email=payload.get("email", ""),
            role=payload.get("role", "viewer"),
        )

    def owns_interactive_endpoints(self) -> bool:
        return False


_default_provider = PgAuthProvider()


def get_default_provider() -> AuthProvider:
    return _default_provider
