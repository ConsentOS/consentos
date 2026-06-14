"""System information endpoints for the admin UI."""

from fastapi import APIRouter, Depends

from src.config.settings import Settings, get_settings
from src.schemas.auth import CurrentUser
from src.services.dependencies import require_role
from src.services.update_check import get_version_info

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/version")
async def get_version(
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return the running version and whether a newer release is available.

    ``latest`` is ``None`` (and ``update_available`` false) when the
    latest version isn't known yet.
    """
    return await get_version_info(settings)
