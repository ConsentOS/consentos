"""Organisation-level default configuration endpoints.

Provides GET and PUT for the organisation's global config defaults.
These defaults sit between system defaults and site config in the cascade.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.org_config import OrgConfig
from src.schemas.auth import CurrentUser
from src.schemas.org_config import OrgConfigResponse, OrgConfigUpdate
from src.services.dependencies import require_role

router = APIRouter(prefix="/org-config", tags=["organisations"])


@router.get("/", response_model=OrgConfigResponse)
async def get_org_config(
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> OrgConfig:
    """Retrieve the organisation's global configuration defaults."""
    result = await db.execute(
        select(OrgConfig).where(OrgConfig.organisation_id == current_user.organisation_id)
    )
    config = result.scalar_one_or_none()

    if config is None:
        # Auto-create an empty config row so the response is always valid
        config = OrgConfig(organisation_id=current_user.organisation_id)
        db.add(config)
        await db.flush()
        await db.refresh(config)

    return config


@router.put("/", response_model=OrgConfigResponse)
async def update_org_config(
    body: OrgConfigUpdate,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> OrgConfig:
    """Create or update the organisation's global configuration defaults.

    Changes the draft of every site that inherits these defaults. Visitors
    see the change once those sites are published: ``GET
    /config/affected-sites`` lists them and ``POST /config/bulk-publish``
    publishes them together.

    Only non-None fields will override system defaults when resolving site config.
    """
    result = await db.execute(
        select(OrgConfig).where(OrgConfig.organisation_id == current_user.organisation_id)
    )
    config = result.scalar_one_or_none()

    if config is None:
        config = OrgConfig(
            organisation_id=current_user.organisation_id,
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
