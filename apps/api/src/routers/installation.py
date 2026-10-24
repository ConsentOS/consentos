"""Whether the banner is installed on a site, and checking it on demand."""

import logging
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import configured_base_url, get_settings
from src.db import get_db
from src.models.site import Site
from src.models.site_installation import SiteInstallation
from src.schemas.auth import CurrentUser
from src.schemas.installation import (
    CheckInstallationRequest,
    InstallationResponse,
    InstallationSummary,
)
from src.services.dependencies import require_role
from src.services.installation import (
    diagnose,
    get_installation,
    installation_state,
    save_check,
)
from src.services.site_domains import host_matches_site, url_host

logger = logging.getLogger(__name__)

# Registered before the sites router, so ``/sites/installations`` isn't
# taken for a site ID.
router = APIRouter(prefix="/sites", tags=["installation"])

CHECK_TIMEOUT_SECONDS = 45


@router.get("/installations", response_model=list[InstallationSummary])
async def list_installations(
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> list[InstallationSummary]:
    """The installation state of every site in the organisation."""
    rows = await db.execute(
        select(Site.id, SiteInstallation)
        .outerjoin(SiteInstallation, SiteInstallation.site_id == Site.id)
        .where(
            Site.organisation_id == current_user.organisation_id,
            Site.deleted_at.is_(None),
        )
    )
    return [
        InstallationSummary(
            site_id=site_id,
            state=installation_state(installation),
            last_seen_at=installation.last_seen_at if installation else None,
        )
        for site_id, installation in rows.all()
    ]


@router.get("/{site_id}/installation", response_model=InstallationResponse)
async def get_site_installation(
    site_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> InstallationResponse:
    """Whether the banner has been seen on the site, and the last check."""
    await _get_org_site(site_id, current_user.organisation_id, db)
    return _response(await get_installation(db, site_id))


@router.post("/{site_id}/installation/check", response_model=InstallationResponse)
async def check_site_installation(
    site_id: uuid.UUID,
    body: CheckInstallationRequest | None = None,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor")),
    db: AsyncSession = Depends(get_db),
) -> InstallationResponse:
    """Load the site's page in the scanner and check how the banner is installed."""
    site = await _get_org_site(site_id, current_user.organisation_id, db)
    url = _page_to_check(site, body.url if body else None)
    settings = get_settings()

    try:
        async with httpx.AsyncClient(timeout=CHECK_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{settings.scanner_service_url}/check-install", json={"url": url}
            )
    except httpx.HTTPError as exc:
        logger.warning("Installation check for site %s failed: %s", site_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The scanner isn't available at the moment. Try again shortly.",
        ) from None
    if resp.status_code == status.HTTP_400_BAD_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The scanner can't load that address.",
        )
    if resp.is_error:
        logger.warning("Scanner returned %s checking site %s", resp.status_code, site_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The scanner couldn't check the site. Try again shortly.",
        )

    now = datetime.now(UTC)
    result = diagnose(
        site,
        resp.json(),
        expected_api_base=configured_base_url(settings.public_api_url),
        checked_at=now,
    )
    await save_check(db, site_id, result, now)
    await db.commit()
    return _response(await get_installation(db, site_id))


async def _get_org_site(
    site_id: uuid.UUID,
    organisation_id: uuid.UUID,
    db: AsyncSession,
) -> Site:
    """Fetch a site ensuring it belongs to the given organisation."""
    result = await db.execute(
        select(Site).where(
            Site.id == site_id,
            Site.organisation_id == organisation_id,
            Site.deleted_at.is_(None),
        )
    )
    site = result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    return site


def _page_to_check(site: Site, url: str | None) -> str:
    if url is None:
        return f"https://{site.domain}/"
    if not url.startswith(("https://", "http://")) or not host_matches_site(url_host(url), site):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Check a page on one of this site's domains.",
        )
    return url


def _response(installation: SiteInstallation | None) -> InstallationResponse:
    if installation is None:
        return InstallationResponse(state="not_detected")
    return InstallationResponse(
        state=installation_state(installation),
        first_seen_at=installation.first_seen_at,
        last_seen_at=installation.last_seen_at,
        last_seen_url=installation.last_seen_url,
        last_check_at=installation.last_check_at,
        last_check=installation.last_check,
    )
