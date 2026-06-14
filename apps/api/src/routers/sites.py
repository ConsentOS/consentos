import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.site import Site
from src.models.site_config import SiteConfig
from src.routers.config import (
    _get_site_group_id,
    _load_group_defaults,
    _load_org_defaults,
)
from src.schemas.auth import CurrentUser
from src.schemas.site import (
    SiteConfigCreate,
    SiteConfigResponse,
    SiteConfigUpdate,
    SiteCreate,
    SiteResponse,
    SiteUpdate,
)
from src.services.config_resolver import orm_to_config_dict, resolve_config
from src.services.dependencies import require_role

router = APIRouter(prefix="/sites", tags=["sites"])


# ── Site CRUD ────────────────────────────────────────────────────────


@router.post("/", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
async def create_site(
    body: SiteCreate,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> Site:
    """Create a new site within the current organisation."""
    # Check domain uniqueness within the org
    existing = await db.execute(
        select(Site).where(
            Site.organisation_id == current_user.organisation_id,
            Site.domain == body.domain,
            Site.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Site with domain '{body.domain}' already exists in this organisation",
        )

    site = Site(
        organisation_id=current_user.organisation_id,
        domain=body.domain,
        display_name=body.display_name,
        site_group_id=body.site_group_id,
    )
    db.add(site)
    await db.flush()

    # Auto-create a default site configuration
    default_config = SiteConfig(site_id=site.id)
    db.add(default_config)
    await db.flush()

    await db.refresh(site)
    return site


@router.get("/", response_model=list[SiteResponse])
async def list_sites(
    site_group_id: uuid.UUID | None = Query(default=None),
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> list[Site]:
    """List all active sites in the current organisation, optionally filtered by group."""
    query = select(Site).where(
        Site.organisation_id == current_user.organisation_id,
        Site.deleted_at.is_(None),
    )
    if site_group_id is not None:
        query = query.where(Site.site_group_id == site_group_id)
    result = await db.execute(query.order_by(Site.domain))
    return list(result.scalars().all())


@router.get("/{site_id}", response_model=SiteResponse)
async def get_site(
    site_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> Site:
    """Get a specific site by ID."""
    site = await _get_org_site(site_id, current_user.organisation_id, db)
    return site


@router.patch("/{site_id}", response_model=SiteResponse)
async def update_site(
    site_id: uuid.UUID,
    body: SiteUpdate,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor")),
    db: AsyncSession = Depends(get_db),
) -> Site:
    """Update a site's display name or active status."""
    site = await _get_org_site(site_id, current_user.organisation_id, db)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(site, field, value)

    await db.flush()
    await db.refresh(site)
    return site


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_site(
    site_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a site."""
    site = await _get_org_site(site_id, current_user.organisation_id, db)
    site.deleted_at = datetime.now(UTC)
    await db.flush()


# ── Site config CRUD ─────────────────────────────────────────────────


async def _editor_response(
    config: SiteConfig, organisation_id: uuid.UUID, db: AsyncSession
) -> dict:
    """Serialise a site_configs row with the cascade applied.

    The admin editor expects effective values for every scalar field:
    NULLs on the row (a cleared override) are replaced with the value
    the resolver would supply from the group / org / system layer. The
    sibling ``/inheritance`` endpoint is the source of truth for *which*
    layer supplied each value; this helper is only concerned with the
    flattened, non-null payload the form needs to render.
    """
    site_dict = orm_to_config_dict(config)
    org_defaults = await _load_org_defaults(organisation_id, db)
    group_id = await _get_site_group_id(config.site_id, db)
    group_defaults = await _load_group_defaults(group_id, db) if group_id else None
    resolved = resolve_config(
        site_dict,
        org_defaults=org_defaults,
        group_defaults=group_defaults,
    )

    return {
        "id": config.id,
        "site_id": config.site_id,
        "created_at": config.created_at,
        "updated_at": config.updated_at,
        "blocking_mode": resolved.get("blocking_mode"),
        "regional_modes": resolved.get("regional_modes"),
        "tcf_enabled": resolved.get("tcf_enabled"),
        "tcf_publisher_cc": resolved.get("tcf_publisher_cc"),
        "gpp_enabled": resolved.get("gpp_enabled"),
        "gpp_supported_apis": resolved.get("gpp_supported_apis"),
        "gpc_enabled": resolved.get("gpc_enabled"),
        "gpc_jurisdictions": resolved.get("gpc_jurisdictions"),
        "gpc_global_honour": resolved.get("gpc_global_honour"),
        "gcm_enabled": resolved.get("gcm_enabled"),
        "gcm_default": resolved.get("gcm_default"),
        "shopify_privacy_enabled": resolved.get("shopify_privacy_enabled"),
        "banner_config": resolved.get("banner_config"),
        "privacy_policy_url": resolved.get("privacy_policy_url"),
        "terms_url": resolved.get("terms_url"),
        "scan_schedule_cron": resolved.get("scan_schedule_cron"),
        "scan_max_pages": resolved.get("scan_max_pages"),
        "consent_expiry_days": resolved.get("consent_expiry_days"),
        "consent_retention_days": config.consent_retention_days,
        "enabled_categories": resolved.get("enabled_categories"),
        "disclosed_vendor_ids": resolved.get("disclosed_vendor_ids"),
    }


@router.get("/{site_id}/config", response_model=SiteConfigResponse)
async def get_site_config(
    site_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get the configuration for a site, with the cascade applied."""
    await _get_org_site(site_id, current_user.organisation_id, db)
    result = await db.execute(select(SiteConfig).where(SiteConfig.site_id == site_id))
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site configuration not found. Create one first.",
        )
    return await _editor_response(config, current_user.organisation_id, db)


@router.put("/{site_id}/config", response_model=SiteConfigResponse)
async def create_or_replace_site_config(
    site_id: uuid.UUID,
    body: SiteConfigCreate,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create or replace the full configuration for a site."""
    await _get_org_site(site_id, current_user.organisation_id, db)

    result = await db.execute(select(SiteConfig).where(SiteConfig.site_id == site_id))
    existing = result.scalar_one_or_none()

    if existing is not None:
        for field, value in body.model_dump().items():
            setattr(existing, field, value)
        await db.flush()
        await db.refresh(existing)
        return await _editor_response(existing, current_user.organisation_id, db)

    config = SiteConfig(site_id=site_id, **body.model_dump())
    db.add(config)
    await db.flush()
    await db.refresh(config)
    return await _editor_response(config, current_user.organisation_id, db)


@router.patch("/{site_id}/config", response_model=SiteConfigResponse)
async def update_site_config(
    site_id: uuid.UUID,
    body: SiteConfigUpdate,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Partially update the configuration for a site."""
    await _get_org_site(site_id, current_user.organisation_id, db)

    result = await db.execute(select(SiteConfig).where(SiteConfig.site_id == site_id))
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site configuration not found. Create one first.",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)

    await db.flush()
    await db.refresh(config)
    return await _editor_response(config, current_user.organisation_id, db)


# ── Helpers ──────────────────────────────────────────────────────────


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
