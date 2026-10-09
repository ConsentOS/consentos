"""Per-site consent analytics dashboard endpoints.

Exposes aggregated consent decisions (accept / partial / decline) for a
single site. All endpoints are tenant-isolated: the site must belong to
the caller's organisation, otherwise a 404 is returned so site existence
is not leaked across tenants.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.site import Site
from src.schemas.analytics import ConsentRatesResponse, ConsentTrendsResponse
from src.schemas.auth import CurrentUser
from src.services.analytics import (
    VALID_GRANULARITIES,
    compute_consent_rates,
    compute_consent_trends,
)
from src.services.dependencies import require_role

router = APIRouter(prefix="/sites", tags=["analytics"])

_VIEW_ROLES = ("owner", "admin", "editor", "viewer")


async def _verify_site_access(
    site_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession,
) -> None:
    """Ensure the site exists and belongs to the caller's organisation."""
    site = (
        await db.execute(
            select(Site.id).where(
                Site.id == site_id,
                Site.organisation_id == current_user.organisation_id,
                Site.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")


@router.get("/{site_id}/consent-rates", response_model=ConsentRatesResponse)
async def get_consent_rates(
    site_id: uuid.UUID,
    days: int = Query(30, ge=1, le=730, description="Trailing window in days"),
    current_user: CurrentUser = Depends(require_role(*_VIEW_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ConsentRatesResponse:
    """Accept / partial / decline breakdown and per-category rates."""
    await _verify_site_access(site_id, current_user, db)
    return await compute_consent_rates(db, site_id, days)


@router.get("/{site_id}/consent-trends", response_model=ConsentTrendsResponse)
async def get_consent_trends(
    site_id: uuid.UUID,
    days: int = Query(30, ge=1, le=730, description="Trailing window in days"),
    granularity: str = Query("day", description="Bucket size: day, week or month"),
    current_user: CurrentUser = Depends(require_role(*_VIEW_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ConsentTrendsResponse:
    """Consent decisions over time, bucketed by ``granularity``."""
    if granularity not in VALID_GRANULARITIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"granularity must be one of {', '.join(VALID_GRANULARITIES)}",
        )
    await _verify_site_access(site_id, current_user, db)
    return await compute_consent_trends(db, site_id, days, granularity)
