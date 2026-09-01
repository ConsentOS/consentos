"""Organisation-level translation management endpoints.

CRUD for per-organisation, per-locale translation strings. These sit
above per-site translations in the cascade (see
``src.services.translation_resolver``) so common strings can be
defined once for every site in the organisation.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.org_translation import OrgTranslation
from src.schemas.auth import CurrentUser
from src.schemas.org_translation import (
    OrgTranslationCreate,
    OrgTranslationResponse,
    OrgTranslationUpdate,
)
from src.services.dependencies import require_role

router = APIRouter(prefix="/org-translations", tags=["translations"])


@router.get("/", response_model=list[OrgTranslationResponse])
async def list_org_translations(
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> list[OrgTranslation]:
    """List all organisation-level translations."""
    result = await db.execute(
        select(OrgTranslation)
        .where(OrgTranslation.organisation_id == current_user.organisation_id)
        .order_by(OrgTranslation.locale)
    )
    return list(result.scalars().all())


@router.get("/{locale}", response_model=OrgTranslationResponse)
async def get_org_translation(
    locale: str,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> OrgTranslation:
    """Get organisation-level translation strings for a specific locale."""
    result = await db.execute(
        select(OrgTranslation).where(
            OrgTranslation.organisation_id == current_user.organisation_id,
            OrgTranslation.locale == locale,
        )
    )
    translation = result.scalar_one_or_none()
    if translation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No organisation translation found for locale '{locale}'",
        )
    return translation


@router.post("/", response_model=OrgTranslationResponse, status_code=status.HTTP_201_CREATED)
async def create_org_translation(
    body: OrgTranslationCreate,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor")),
    db: AsyncSession = Depends(get_db),
) -> OrgTranslation:
    """Create an organisation-level translation for a new locale."""
    existing = await db.execute(
        select(OrgTranslation).where(
            OrgTranslation.organisation_id == current_user.organisation_id,
            OrgTranslation.locale == body.locale,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Organisation translation for locale '{body.locale}' already exists",
        )

    translation = OrgTranslation(
        organisation_id=current_user.organisation_id,
        locale=body.locale,
        strings=body.strings,
    )
    db.add(translation)
    await db.flush()
    await db.refresh(translation)
    return translation


@router.put("/{locale}", response_model=OrgTranslationResponse)
async def update_org_translation(
    locale: str,
    body: OrgTranslationUpdate,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor")),
    db: AsyncSession = Depends(get_db),
) -> OrgTranslation:
    """Replace the strings for an existing organisation-level locale translation."""
    result = await db.execute(
        select(OrgTranslation).where(
            OrgTranslation.organisation_id == current_user.organisation_id,
            OrgTranslation.locale == locale,
        )
    )
    translation = result.scalar_one_or_none()
    if translation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No organisation translation found for locale '{locale}'",
        )

    translation.strings = body.strings
    await db.flush()
    await db.refresh(translation)
    return translation


@router.delete("/{locale}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org_translation(
    locale: str,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an organisation-level translation for a specific locale."""
    result = await db.execute(
        select(OrgTranslation).where(
            OrgTranslation.organisation_id == current_user.organisation_id,
            OrgTranslation.locale == locale,
        )
    )
    translation = result.scalar_one_or_none()
    if translation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No organisation translation found for locale '{locale}'",
        )
    await db.delete(translation)
    await db.flush()
