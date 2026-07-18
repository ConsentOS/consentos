from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.extensions.registry import get_registry
from src.schemas.auth import CurrentUser
from src.services.auth_provider import get_default_provider

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> CurrentUser:
    """Delegate to the registered auth provider, or the PG default."""
    provider = get_registry().auth_provider or get_default_provider()
    return await provider.verify_token(credentials.credentials)


def require_role(*allowed_roles: str) -> Callable:
    """Dependency factory that restricts access to users with specific roles."""

    async def _check_role(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if not current_user.has_role(*allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not permitted for this action",
            )
        return current_user

    return _check_role
