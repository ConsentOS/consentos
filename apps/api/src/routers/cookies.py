"""Cookie category, cookie, and allow-list management endpoints."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.cookie import Cookie, CookieAllowListEntry, CookieCategory, KnownCookie
from src.models.site import Site
from src.schemas.auth import CurrentUser
from src.schemas.cookie import (
    AllowListEntryCreate,
    AllowListEntryResponse,
    AllowListEntryUpdate,
    ClassificationResultResponse,
    ClassifySingleRequest,
    ClassifySiteResponse,
    CookieCategoryResponse,
    CookieCreate,
    CookieResponse,
    CookieUpdate,
    KnownCookieCreate,
    KnownCookieResponse,
    KnownCookieUpdate,
    ReviewStatus,
)
from src.services.classification import classify_single_cookie, classify_site_cookies
from src.services.dependencies import get_current_user, require_role

router = APIRouter(prefix="/cookies", tags=["cookies"])


# ── Cookie categories (read-only, seeded by migration) ──────────────


@router.get("/categories", response_model=list[CookieCategoryResponse])
async def list_categories(
    db: AsyncSession = Depends(get_db),
) -> list[CookieCategory]:
    """List all cookie categories. Public endpoint used by banner and admin."""
    result = await db.execute(select(CookieCategory).order_by(CookieCategory.display_order))
    return list(result.scalars().all())


@router.get("/categories/{category_id}", response_model=CookieCategoryResponse)
async def get_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CookieCategory:
    """Get a single cookie category by ID."""
    result = await db.execute(select(CookieCategory).where(CookieCategory.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


# ── Cookies per site ─────────────────────────────────────────────────


async def _get_org_site(
    site_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession,
) -> Site:
    """Fetch a site ensuring it belongs to the user's organisation."""
    result = await db.execute(
        select(Site).where(
            Site.id == site_id,
            Site.organisation_id == current_user.organisation_id,
            Site.deleted_at.is_(None),
        )
    )
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    return site


@router.get(
    "/sites/{site_id}",
    response_model=list[CookieResponse],
)
async def list_cookies(
    site_id: uuid.UUID,
    review_status: ReviewStatus | None = Query(None),
    category_id: uuid.UUID | None = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Cookie]:
    """List cookies discovered on a site, with optional filters."""
    await _get_org_site(site_id, current_user, db)

    query = select(Cookie).where(Cookie.site_id == site_id)
    if review_status:
        query = query.where(Cookie.review_status == review_status.value)
    if category_id:
        query = query.where(Cookie.category_id == category_id)
    query = query.order_by(Cookie.name)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.post(
    "/sites/{site_id}",
    response_model=CookieResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_cookie(
    site_id: uuid.UUID,
    body: CookieCreate,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor")),
    db: AsyncSession = Depends(get_db),
) -> Cookie:
    """Create a cookie record for a site (manual entry or from scanner)."""
    await _get_org_site(site_id, current_user, db)

    # Validate category if provided
    if body.category_id:
        cat = await db.execute(select(CookieCategory).where(CookieCategory.id == body.category_id))
        if not cat.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid category_id",
            )

    # Enforce the (site_id, name, domain, storage_type) uniqueness up front
    # so a manual duplicate returns a clean 409 instead of a flush-time
    # IntegrityError → 500. The scanner/reporter paths upsert and never
    # reach this endpoint, but the admin "Add cookie" form can.
    existing = await db.execute(
        select(Cookie).where(
            Cookie.site_id == site_id,
            Cookie.name == body.name,
            Cookie.domain == body.domain,
            Cookie.storage_type == body.storage_type,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cookie '{body.name}' on '{body.domain}' already exists for this site",
        )

    cookie = Cookie(
        site_id=site_id,
        **body.model_dump(),
        first_seen_at=datetime.now(UTC).isoformat(),
        last_seen_at=datetime.now(UTC).isoformat(),
    )
    db.add(cookie)
    await db.flush()
    await db.refresh(cookie)
    return cookie


@router.get("/sites/{site_id}/summary")
async def cookie_summary(
    site_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a summary of cookies for a site (counts by status and category)."""
    await _get_org_site(site_id, current_user, db)

    # Count by review status
    status_result = await db.execute(
        select(Cookie.review_status, func.count(Cookie.id))
        .where(Cookie.site_id == site_id)
        .group_by(Cookie.review_status)
    )
    by_status = {row[0]: row[1] for row in status_result.all()}

    # Count by category
    cat_result = await db.execute(
        select(CookieCategory.slug, func.count(Cookie.id))
        .outerjoin(Cookie, Cookie.category_id == CookieCategory.id)
        .where(Cookie.site_id == site_id)
        .group_by(CookieCategory.slug)
    )
    by_category = {row[0]: row[1] for row in cat_result.all()}

    # Uncategorised count
    uncat_result = await db.execute(
        select(func.count(Cookie.id)).where(Cookie.site_id == site_id, Cookie.category_id.is_(None))
    )
    uncategorised = uncat_result.scalar() or 0

    return {
        "total": sum(by_status.values()),
        "by_status": by_status,
        "by_category": by_category,
        "uncategorised": uncategorised,
    }


# ── Allow-list per site ──────────────────────────────────────────────
# (Must be defined before {cookie_id} routes to avoid path conflicts)


@router.get(
    "/sites/{site_id}/allow-list",
    response_model=list[AllowListEntryResponse],
)
async def list_allow_list(
    site_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CookieAllowListEntry]:
    """List all allow-list entries for a site."""
    await _get_org_site(site_id, current_user, db)

    result = await db.execute(
        select(CookieAllowListEntry)
        .where(CookieAllowListEntry.site_id == site_id)
        .order_by(CookieAllowListEntry.name_pattern)
    )
    return list(result.scalars().all())


@router.post(
    "/sites/{site_id}/allow-list",
    response_model=AllowListEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_allow_list_entry(
    site_id: uuid.UUID,
    body: AllowListEntryCreate,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor")),
    db: AsyncSession = Depends(get_db),
) -> CookieAllowListEntry:
    """Add a cookie pattern to the allow-list for a site."""
    await _get_org_site(site_id, current_user, db)

    # Validate category
    cat = await db.execute(select(CookieCategory).where(CookieCategory.id == body.category_id))
    if not cat.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid category_id",
        )

    entry = CookieAllowListEntry(
        site_id=site_id,
        **body.model_dump(),
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.patch(
    "/sites/{site_id}/allow-list/{entry_id}",
    response_model=AllowListEntryResponse,
)
async def update_allow_list_entry(
    site_id: uuid.UUID,
    entry_id: uuid.UUID,
    body: AllowListEntryUpdate,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor")),
    db: AsyncSession = Depends(get_db),
) -> CookieAllowListEntry:
    """Update an allow-list entry."""
    await _get_org_site(site_id, current_user, db)

    result = await db.execute(
        select(CookieAllowListEntry).where(
            CookieAllowListEntry.id == entry_id,
            CookieAllowListEntry.site_id == site_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Allow-list entry not found",
        )

    updates = body.model_dump(exclude_unset=True)

    if "category_id" in updates and updates["category_id"] is not None:
        cat = await db.execute(
            select(CookieCategory).where(CookieCategory.id == updates["category_id"])
        )
        if not cat.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid category_id",
            )

    for field, value in updates.items():
        setattr(entry, field, value)
    entry.updated_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete(
    "/sites/{site_id}/allow-list/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_allow_list_entry(
    site_id: uuid.UUID,
    entry_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove an entry from the allow-list."""
    await _get_org_site(site_id, current_user, db)

    result = await db.execute(
        select(CookieAllowListEntry).where(
            CookieAllowListEntry.id == entry_id,
            CookieAllowListEntry.site_id == site_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Allow-list entry not found",
        )

    await db.delete(entry)


# ── Individual cookie by ID (must come after /summary and /allow-list) ──


@router.get("/sites/{site_id}/{cookie_id}", response_model=CookieResponse)
async def get_cookie(
    site_id: uuid.UUID,
    cookie_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Cookie:
    """Get a single cookie by ID."""
    await _get_org_site(site_id, current_user, db)

    result = await db.execute(
        select(Cookie).where(Cookie.id == cookie_id, Cookie.site_id == site_id)
    )
    cookie = result.scalar_one_or_none()
    if not cookie:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cookie not found")
    return cookie


@router.patch("/sites/{site_id}/{cookie_id}", response_model=CookieResponse)
async def update_cookie(
    site_id: uuid.UUID,
    cookie_id: uuid.UUID,
    body: CookieUpdate,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor")),
    db: AsyncSession = Depends(get_db),
) -> Cookie:
    """Update a cookie record (e.g. assign category, change review status)."""
    await _get_org_site(site_id, current_user, db)

    result = await db.execute(
        select(Cookie).where(Cookie.id == cookie_id, Cookie.site_id == site_id)
    )
    cookie = result.scalar_one_or_none()
    if not cookie:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cookie not found")

    updates = body.model_dump(exclude_unset=True)

    # Validate category if being changed
    if "category_id" in updates and updates["category_id"] is not None:
        cat = await db.execute(
            select(CookieCategory).where(CookieCategory.id == updates["category_id"])
        )
        if not cat.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid category_id",
            )

    for field, value in updates.items():
        setattr(cookie, field, value)
    cookie.updated_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(cookie)
    return cookie


@router.delete(
    "/sites/{site_id}/{cookie_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_cookie(
    site_id: uuid.UUID,
    cookie_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a cookie record."""
    await _get_org_site(site_id, current_user, db)

    result = await db.execute(
        select(Cookie).where(Cookie.id == cookie_id, Cookie.site_id == site_id)
    )
    cookie = result.scalar_one_or_none()
    if not cookie:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cookie not found")

    await db.delete(cookie)


# ── Known cookies database ──────────────────────────────────────────


@router.get("/known", response_model=list[KnownCookieResponse])
async def list_known_cookies(
    vendor: str | None = Query(None, description="Filter by vendor name"),
    search: str | None = Query(None, description="Search by name pattern"),
    db: AsyncSession = Depends(get_db),
    _user: CurrentUser = Depends(get_current_user),
) -> list[KnownCookie]:
    """List known cookie patterns from the shared database."""
    query = select(KnownCookie).order_by(KnownCookie.name_pattern)
    if vendor:
        query = query.where(KnownCookie.vendor == vendor)
    if search:
        query = query.where(KnownCookie.name_pattern.ilike(f"%{search}%"))
    result = await db.execute(query)
    return list(result.scalars().all())


@router.post(
    "/known",
    response_model=KnownCookieResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_known_cookie(
    body: KnownCookieCreate,
    _user: CurrentUser = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> KnownCookie:
    """Add a new pattern to the known cookies database."""
    # Validate category
    cat = await db.execute(select(CookieCategory).where(CookieCategory.id == body.category_id))
    if not cat.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid category_id",
        )

    known = KnownCookie(**body.model_dump())
    db.add(known)
    await db.flush()
    await db.refresh(known)
    return known


@router.get("/known/{known_id}", response_model=KnownCookieResponse)
async def get_known_cookie(
    known_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: CurrentUser = Depends(get_current_user),
) -> KnownCookie:
    """Get a single known cookie pattern by ID."""
    result = await db.execute(select(KnownCookie).where(KnownCookie.id == known_id))
    known = result.scalar_one_or_none()
    if not known:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Known cookie not found",
        )
    return known


@router.patch("/known/{known_id}", response_model=KnownCookieResponse)
async def update_known_cookie(
    known_id: uuid.UUID,
    body: KnownCookieUpdate,
    _user: CurrentUser = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> KnownCookie:
    """Update a known cookie pattern."""
    result = await db.execute(select(KnownCookie).where(KnownCookie.id == known_id))
    known = result.scalar_one_or_none()
    if not known:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Known cookie not found",
        )

    updates = body.model_dump(exclude_unset=True)
    if "category_id" in updates and updates["category_id"] is not None:
        cat = await db.execute(
            select(CookieCategory).where(CookieCategory.id == updates["category_id"])
        )
        if not cat.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid category_id",
            )

    for field, value in updates.items():
        setattr(known, field, value)
    known.updated_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(known)
    return known


@router.delete(
    "/known/{known_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_known_cookie(
    known_id: uuid.UUID,
    _user: CurrentUser = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a known cookie pattern."""
    result = await db.execute(select(KnownCookie).where(KnownCookie.id == known_id))
    known = result.scalar_one_or_none()
    if not known:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Known cookie not found",
        )
    await db.delete(known)


# ── Classification endpoints ────────────────────────────────────────


@router.post(
    "/sites/{site_id}/classify",
    response_model=ClassifySiteResponse,
)
async def classify_cookies(
    site_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor")),
    db: AsyncSession = Depends(get_db),
) -> ClassifySiteResponse:
    """Auto-classify pending cookies for a site against known patterns."""
    await _get_org_site(site_id, current_user, db)

    results = await classify_site_cookies(db, site_id, only_pending=True)
    matched_count = sum(1 for r in results if r.matched)

    return ClassifySiteResponse(
        site_id=str(site_id),
        total=len(results),
        matched=matched_count,
        unmatched=len(results) - matched_count,
        results=[
            ClassificationResultResponse(
                cookie_name=r.cookie_name,
                cookie_domain=r.cookie_domain,
                category_id=r.category_id,
                category_slug=r.category_slug,
                vendor=r.vendor,
                description=r.description,
                match_source=r.match_source,
                matched=r.matched,
            )
            for r in results
        ],
    )


@router.post(
    "/sites/{site_id}/classify/preview",
    response_model=ClassificationResultResponse,
)
async def classify_preview(
    site_id: uuid.UUID,
    body: ClassifySingleRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ClassificationResultResponse:
    """Preview classification for a single cookie without saving."""
    await _get_org_site(site_id, current_user, db)

    result = await classify_single_cookie(db, site_id, body.cookie_name, body.cookie_domain)
    return ClassificationResultResponse(
        cookie_name=result.cookie_name,
        cookie_domain=result.cookie_domain,
        category_id=result.category_id,
        category_slug=result.category_slug,
        vendor=result.vendor,
        description=result.description,
        match_source=result.match_source,
        matched=result.matched,
    )
