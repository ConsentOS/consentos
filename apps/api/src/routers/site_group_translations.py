"""Site-group-level translation management endpoints.

CRUD for per-site-group, per-locale translation strings. These sit
between org-level and per-site translations in the cascade (see
``src.services.translation_resolver``).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.site_group import SiteGroup
from src.models.site_group_translation import SiteGroupTranslation
from src.schemas.auth import CurrentUser
from src.schemas.site_group_translation import (
    SiteGroupTranslationCreate,
    SiteGroupTranslationResponse,
    SiteGroupTranslationUpdate,
)
from src.services.dependencies import require_role

router = APIRouter(prefix="/site-groups/{group_id}/translations", tags=["site-groups"])


async def _verify_group_ownership(
    group_id: uuid.UUID,
    organisation_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Ensure the site group belongs to the user's organisation."""
    result = await db.execute(
        select(SiteGroup).where(
            SiteGroup.id == group_id,
            SiteGroup.organisation_id == organisation_id,
            SiteGroup.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site group not found",
        )


@router.get("/", response_model=list[SiteGroupTranslationResponse])
async def list_group_translations(
    group_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> list[SiteGroupTranslation]:
    """List all translations for a site group."""
    await _verify_group_ownership(group_id, current_user.organisation_id, db)
    result = await db.execute(
        select(SiteGroupTranslation)
        .where(SiteGroupTranslation.site_group_id == group_id)
        .order_by(SiteGroupTranslation.locale)
    )
    return list(result.scalars().all())


@router.get("/{locale}", response_model=SiteGroupTranslationResponse)
async def get_group_translation(
    group_id: uuid.UUID,
    locale: str,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> SiteGroupTranslation:
    """Get translation strings for a specific locale within a site group."""
    await _verify_group_ownership(group_id, current_user.organisation_id, db)
    result = await db.execute(
        select(SiteGroupTranslation).where(
            SiteGroupTranslation.site_group_id == group_id,
            SiteGroupTranslation.locale == locale,
        )
    )
    translation = result.scalar_one_or_none()
    if translation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No group translation found for locale '{locale}'",
        )
    return translation


@router.post("/", response_model=SiteGroupTranslationResponse, status_code=status.HTTP_201_CREATED)
async def create_group_translation(
    group_id: uuid.UUID,
    body: SiteGroupTranslationCreate,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor")),
    db: AsyncSession = Depends(get_db),
) -> SiteGroupTranslation:
    """Create a site-group translation for a new locale."""
    await _verify_group_ownership(group_id, current_user.organisation_id, db)

    existing = await db.execute(
        select(SiteGroupTranslation).where(
            SiteGroupTranslation.site_group_id == group_id,
            SiteGroupTranslation.locale == body.locale,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Group translation for locale '{body.locale}' already exists",
        )

    translation = SiteGroupTranslation(
        site_group_id=group_id,
        locale=body.locale,
        strings=body.strings,
    )
    db.add(translation)
    await db.flush()
    await db.refresh(translation)
    return translation


@router.put("/{locale}", response_model=SiteGroupTranslationResponse)
async def update_group_translation(
    group_id: uuid.UUID,
    locale: str,
    body: SiteGroupTranslationUpdate,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor")),
    db: AsyncSession = Depends(get_db),
) -> SiteGroupTranslation:
    """Replace the strings for an existing site-group locale translation."""
    await _verify_group_ownership(group_id, current_user.organisation_id, db)
    result = await db.execute(
        select(SiteGroupTranslation).where(
            SiteGroupTranslation.site_group_id == group_id,
            SiteGroupTranslation.locale == locale,
        )
    )
    translation = result.scalar_one_or_none()
    if translation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No group translation found for locale '{locale}'",
        )

    translation.strings = body.strings
    await db.flush()
    await db.refresh(translation)
    return translation


@router.delete("/{locale}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group_translation(
    group_id: uuid.UUID,
    locale: str,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a site-group translation for a specific locale."""
    await _verify_group_ownership(group_id, current_user.organisation_id, db)
    result = await db.execute(
        select(SiteGroupTranslation).where(
            SiteGroupTranslation.site_group_id == group_id,
            SiteGroupTranslation.locale == locale,
        )
    )
    translation = result.scalar_one_or_none()
    if translation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No group translation found for locale '{locale}'",
        )
    await db.delete(translation)
    await db.flush()
