"""Site-group-level default configuration endpoints.

Provides GET and PUT for a site group's config defaults.
These defaults sit between org defaults and site config in the cascade.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.site_group import SiteGroup
from src.models.site_group_config import SiteGroupConfig
from src.schemas.auth import CurrentUser
from src.schemas.site_group_config import SiteGroupConfigResponse, SiteGroupConfigUpdate
from src.services.dependencies import require_role

router = APIRouter(prefix="/site-groups", tags=["site-groups"])


@router.get("/{group_id}/config", response_model=SiteGroupConfigResponse)
async def get_site_group_config(
    group_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> SiteGroupConfig:
    """Retrieve configuration defaults for a site group."""
    await _verify_group_ownership(group_id, current_user.organisation_id, db)

    result = await db.execute(
        select(SiteGroupConfig).where(SiteGroupConfig.site_group_id == group_id)
    )
    config = result.scalar_one_or_none()

    if config is None:
        # Auto-create an empty config row so the response is always valid
        config = SiteGroupConfig(site_group_id=group_id)
        db.add(config)
        await db.flush()
        await db.refresh(config)

    return config


@router.put("/{group_id}/config", response_model=SiteGroupConfigResponse)
async def update_site_group_config(
    group_id: uuid.UUID,
    body: SiteGroupConfigUpdate,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> SiteGroupConfig:
    """Create or update configuration defaults for a site group.

    Changes the draft of every site that inherits these defaults. Visitors
    see the change once those sites are published: ``GET
    /config/affected-sites`` lists them and ``POST /config/bulk-publish``
    publishes them together.

    Only non-None fields will override org/system defaults when resolving site config.
    """
    await _verify_group_ownership(group_id, current_user.organisation_id, db)

    result = await db.execute(
        select(SiteGroupConfig).where(SiteGroupConfig.site_group_id == group_id)
    )
    config = result.scalar_one_or_none()

    if config is None:
        config = SiteGroupConfig(
            site_group_id=group_id,
            **body.model_dump(exclude_unset=True),
        )
        db.add(config)
    else:
        update_data = body.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(config, field, value)

    await db.flush()
    await db.refresh(config)
    return config


# -- Helpers ------------------------------------------------------------------


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
