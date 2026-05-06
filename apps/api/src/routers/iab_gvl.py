"""IAB Global Vendor List read endpoints.

Public, unauthenticated endpoints exposing the locally-cached IAB GVL.
The cache is refreshed daily by ``src.tasks.iab_gvl.refresh_gvl``;
these endpoints never hit IAB directly.

Endpoints are intentionally minimal: ``GET /iab/gvl-meta`` for the
current version and ``GET /iab/vendors`` for a paginated list (with an
optional ``q`` filter on name and an ``include_deleted`` flag). The
admin UI vendor picker uses these; banners do not (the banner is
config-driven, not GVL-driven).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.iab_gvl import IabGvlMeta, IabVendor
from src.schemas.iab_gvl import (
    GvlMetaResponse,
    IabVendorListResponse,
    IabVendorResponse,
)

router = APIRouter(prefix="/iab", tags=["iab-gvl"])


@router.get("/gvl-meta", response_model=GvlMetaResponse)
async def get_gvl_meta(db: Annotated[AsyncSession, Depends(get_db)]) -> IabGvlMeta:
    """Return the version metadata for the currently-cached GVL.

    404s when the cache hasn't been populated yet — operators should
    invoke the daily Celery refresh manually on first deploy or wait
    for the schedule to fire.
    """
    meta = (await db.execute(select(IabGvlMeta).limit(1))).scalar_one_or_none()
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="GVL has not been synced yet",
        )
    return meta


@router.get("/vendors", response_model=IabVendorListResponse)
async def list_vendors(
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[str | None, Query(description="Case-insensitive name filter")] = None,
    include_deleted: Annotated[
        bool,
        Query(description="Include vendors that IAB has flagged as deleted"),
    ] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> IabVendorListResponse:
    """List IAB vendors with optional name filter and pagination."""
    base = select(IabVendor)
    if not include_deleted:
        base = base.where(IabVendor.deleted_date.is_(None))
    if q:
        base = base.where(IabVendor.name.ilike(f"%{q}%"))

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        (await db.execute(base.order_by(IabVendor.id).limit(limit).offset(offset))).scalars().all()
    )

    return IabVendorListResponse(
        items=[IabVendorResponse.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/vendors/{vendor_id}", response_model=IabVendorResponse)
async def get_vendor(
    vendor_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IabVendor:
    """Return a single vendor by IAB ID."""
    vendor = (
        await db.execute(select(IabVendor).where(IabVendor.id == vendor_id))
    ).scalar_one_or_none()
    if vendor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor not found",
        )
    return vendor
