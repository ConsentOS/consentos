import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.extensions.registry import get_registry
from src.models.site import Site
from src.models.user import User
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


async def get_org_site(
    site_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Site:
    """Load a non-deleted site in the current user's organisation, else 404."""
    result = await db.execute(
        select(Site).where(
            Site.id == site_id,
            Site.organisation_id == current_user.organisation_id,
            Site.deleted_at.is_(None),
        )
    )
    site = result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    return site


async def require_superuser(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Restrict access to platform admins.

    The flag is read from the database rather than the token so that
    granting or revoking it takes effect immediately. Use this only for
    instance-wide data such as the known cookies list; it does not grant
    access to other organisations' resources.
    """
    is_superuser = await db.scalar(
        select(User.is_superuser).where(
            User.id == current_user.id,
            User.deleted_at.is_(None),
        )
    )
    if not is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin access is required for this action",
        )
    return current_user
