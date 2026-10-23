"""The setup checklist for each site."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.site import Site
from src.schemas.auth import CurrentUser
from src.schemas.site_setup import SiteSetupResponse, SiteSetupSummary
from src.services.dependencies import require_role
from src.services.site_setup import load_setup_facts, summarise

# Registered before the sites router, so ``/sites/setup-summary`` isn't
# taken for a site ID.
router = APIRouter(prefix="/sites", tags=["setup"])


@router.get("/setup-summary", response_model=list[SiteSetupSummary])
async def list_site_setup(
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """How far through setup each site in the organisation is."""
    result = await db.execute(
        select(Site).where(
            Site.organisation_id == current_user.organisation_id,
            Site.deleted_at.is_(None),
        )
    )
    sites = list(result.scalars().all())
    facts = await load_setup_facts(db, sites)
    summaries = []
    for site in sites:
        summary = summarise(facts[site.id])
        del summary["steps"]
        summaries.append({"site_id": site.id, **summary})
    return summaries


@router.get("/{site_id}/setup", response_model=SiteSetupResponse)
async def get_site_setup(
    site_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Each step of the site's setup checklist, with its status."""
    site = await _get_org_site(site_id, current_user.organisation_id, db)
    return await _setup(db, site)


@router.post("/{site_id}/setup/banner-confirmed", response_model=SiteSetupResponse)
async def confirm_site_banner(
    site_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Record that the owner is happy with the banner as it is."""
    site = await _get_org_site(site_id, current_user.organisation_id, db)
    if site.banner_confirmed_at is None:
        site.banner_confirmed_at = datetime.now(UTC)
        await db.flush()
    return await _setup(db, site)


@router.post("/{site_id}/setup/dismiss", response_model=SiteSetupResponse)
async def dismiss_site_setup(
    site_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Hide the finished checklist. Refused until every step is done."""
    site = await _get_org_site(site_id, current_user.organisation_id, db)
    setup = await _setup(db, site)
    if not setup["complete"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Finish every step before dismissing the checklist.",
        )
    if site.setup_dismissed_at is None:
        site.setup_dismissed_at = datetime.now(UTC)
        await db.flush()
    setup["dismissed"] = True
    return setup


async def _setup(db: AsyncSession, site: Site) -> dict:
    facts = await load_setup_facts(db, [site])
    return summarise(facts[site.id])


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
