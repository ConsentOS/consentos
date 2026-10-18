"""Translation management endpoints.

CRUD for per-site, per-locale translation strings used by the banner script.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.site import Site
from src.models.translation import Translation
from src.schemas.auth import CurrentUser
from src.schemas.translation import TranslationCreate, TranslationResponse, TranslationUpdate
from src.services.dependencies import require_role

router = APIRouter(prefix="/sites/{site_id}/translations", tags=["translations"])


async def _get_org_site(site_id: uuid.UUID, organisation_id: uuid.UUID, db: AsyncSession) -> Site:
    """Ensure site belongs to the current organisation."""
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


@router.get("/", response_model=list[TranslationResponse])
async def list_translations(
    site_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> list[Translation]:
    """List all translations for a site."""
    await _get_org_site(site_id, current_user.organisation_id, db)
    result = await db.execute(
        select(Translation).where(Translation.site_id == site_id).order_by(Translation.locale)
    )
    return list(result.scalars().all())


@router.get("/{locale}", response_model=TranslationResponse)
async def get_translation(
    site_id: uuid.UUID,
    locale: str,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> Translation:
    """Get translation strings for a specific locale."""
    await _get_org_site(site_id, current_user.organisation_id, db)
    result = await db.execute(
        select(Translation).where(
            Translation.site_id == site_id,
            Translation.locale == locale,
        )
    )
    translation = result.scalar_one_or_none()
    if translation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No translation found for locale '{locale}'",
        )
    return translation


@router.post("/", response_model=TranslationResponse, status_code=status.HTTP_201_CREATED)
async def create_translation(
    site_id: uuid.UUID,
    body: TranslationCreate,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor")),
    db: AsyncSession = Depends(get_db),
) -> Translation:
    """Create a translation for a new locale.

    Changes the draft only. Visitors see it once the site is published
    with ``POST /config/sites/{site_id}/publish``.
    """
    await _get_org_site(site_id, current_user.organisation_id, db)

    # Check for duplicate locale
    existing = await db.execute(
        select(Translation).where(
            Translation.site_id == site_id,
            Translation.locale == body.locale,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Translation for locale '{body.locale}' already exists",
        )

    translation = Translation(
        site_id=site_id,
        locale=body.locale,
        strings=body.strings,
    )
    db.add(translation)
    await db.flush()
    await db.refresh(translation)
    return translation


@router.put("/{locale}", response_model=TranslationResponse)
async def update_translation(
    site_id: uuid.UUID,
    locale: str,
    body: TranslationUpdate,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor")),
    db: AsyncSession = Depends(get_db),
) -> Translation:
    """Replace the strings for an existing locale translation.

    Changes the draft only. Visitors see it once the site is published
    with ``POST /config/sites/{site_id}/publish``.
    """
    await _get_org_site(site_id, current_user.organisation_id, db)
    result = await db.execute(
        select(Translation).where(
            Translation.site_id == site_id,
            Translation.locale == locale,
        )
    )
    translation = result.scalar_one_or_none()
    if translation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No translation found for locale '{locale}'",
        )

    translation.strings = body.strings
    await db.flush()
    await db.refresh(translation)
    return translation


@router.delete("/{locale}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_translation(
    site_id: uuid.UUID,
    locale: str,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a translation for a specific locale.

    Changes the draft only. Visitors see it once the site is published
    with ``POST /config/sites/{site_id}/publish``.
    """
    await _get_org_site(site_id, current_user.organisation_id, db)
    result = await db.execute(
        select(Translation).where(
            Translation.site_id == site_id,
            Translation.locale == locale,
        )
    )
    translation = result.scalar_one_or_none()
    if translation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No translation found for locale '{locale}'",
        )
    await db.delete(translation)
    await db.flush()


# ── Public endpoint for the banner script ────────────────────────────

public_router = APIRouter(prefix="/translations", tags=["translations"])


@public_router.get("/{site_id}/{locale}")
async def get_public_translation(
    site_id: uuid.UUID,
    locale: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Public endpoint: return translation strings for the banner script.

    No auth required. Returns the raw strings dict for a given site and locale.
    Returns 404 if no translation exists (banner falls back to English defaults).
    """
    result = await db.execute(
        select(Translation)
        .join(Site)
        .where(
            Translation.site_id == site_id,
            Translation.locale == locale,
            Site.is_active.is_(True),
            Site.deleted_at.is_(None),
        )
    )
    translation = result.scalar_one_or_none()
    if translation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Translation not found",
        )
    return translation.strings
