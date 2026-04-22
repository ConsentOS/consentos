import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.extensions.registry import get_registry
from src.models.org_config import OrgConfig
from src.models.site import Site
from src.models.site_config import SiteConfig
from src.models.site_group_config import SiteGroupConfig
from src.schemas.auth import CurrentUser
from src.schemas.site import SiteConfigResponse
from src.services.config_resolver import (
    CONFIG_FIELDS,
    build_public_config,
    orm_to_config_dict,
    resolve_config,
)
from src.services.dependencies import require_role
from src.services.geoip import detect_region
from src.services.publisher import publish_site_config

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/sites/{site_id}", response_model=SiteConfigResponse)
async def get_public_site_config(
    site_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SiteConfig:
    """Public endpoint: retrieve site config for the banner script. No auth required."""
    result = await db.execute(
        select(SiteConfig)
        .join(Site)
        .where(
            SiteConfig.site_id == site_id,
            Site.is_active.is_(True),
            Site.deleted_at.is_(None),
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site configuration not found",
        )
    return config


@router.get("/sites/{site_id}/resolved")
async def get_resolved_config(
    site_id: uuid.UUID,
    region: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Public endpoint: retrieve fully resolved config with regional overrides applied.

    Applies the full cascade: System → Org → Group → Site → Regional.
    """
    result = await db.execute(
        select(SiteConfig)
        .join(Site)
        .where(
            SiteConfig.site_id == site_id,
            Site.is_active.is_(True),
            Site.deleted_at.is_(None),
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site configuration not found",
        )

    config_dict = orm_to_config_dict(config, include_id=True)

    # Load org defaults via the site
    org_id = await _get_site_org_id(site_id, db)
    org_defaults = await _load_org_defaults(org_id, db) if org_id else None

    # Load site group defaults
    group_id = await _get_site_group_id(site_id, db)
    group_defaults = await _load_group_defaults(group_id, db) if group_id else None

    resolved = resolve_config(
        config_dict,
        org_defaults=org_defaults,
        group_defaults=group_defaults,
        region=region,
    )

    # Set consent_group_id when cross-domain sharing is enabled on the
    # group. The banner uses this as the signal to activate the iframe
    # bridge.
    if group_id and resolved.get("consent_sharing_enabled"):
        resolved["consent_group_id"] = str(group_id)
        if resolved.get("consent_bridge_url"):
            resolved["consent_bridge_url"] = resolved["consent_bridge_url"]

    return build_public_config(str(site_id), resolved)


@router.get("/sites/{site_id}/geo-resolved")
async def get_geo_resolved_config(
    site_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Public endpoint: resolve config using the visitor's detected region.

    Detects the visitor's region from CDN headers or IP geolocation,
    then applies regional blocking mode overrides automatically.
    Uses the full cascade: System → Org → Group → Site → Regional.
    """
    result = await db.execute(
        select(SiteConfig)
        .join(Site)
        .where(
            SiteConfig.site_id == site_id,
            Site.is_active.is_(True),
            Site.deleted_at.is_(None),
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site configuration not found",
        )

    # Detect region from request
    geo = await detect_region(request)

    config_dict = orm_to_config_dict(config, include_id=True)
    org_id = await _get_site_org_id(site_id, db)
    org_defaults = await _load_org_defaults(org_id, db) if org_id else None
    group_id = await _get_site_group_id(site_id, db)
    group_defaults = await _load_group_defaults(group_id, db) if group_id else None

    resolved = resolve_config(
        config_dict,
        org_defaults=org_defaults,
        group_defaults=group_defaults,
        region=geo.region,
    )
    public = build_public_config(str(site_id), resolved)

    # Include detected geo info so the banner can use it
    public["detected_country"] = geo.country_code
    public["detected_region"] = geo.region

    return public


@router.get("/geo")
async def get_visitor_geo(request: Request) -> dict:
    """Public endpoint: return the detected region for the current visitor.

    Useful for banner scripts that need to know the region before
    fetching the full config.
    """
    geo = await detect_region(request)
    return {
        "country_code": geo.country_code,
        "region": geo.region,
    }


@router.get("/sites/{site_id}/inheritance")
async def get_config_inheritance(
    site_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the full config inheritance chain for a site.

    Shows the value at each level so the UI can display where each setting
    comes from: system, org, group, or site.
    """
    from src.services.config_resolver import SYSTEM_DEFAULTS

    result = await db.execute(
        select(SiteConfig)
        .join(Site)
        .where(
            SiteConfig.site_id == site_id,
            Site.organisation_id == current_user.organisation_id,
            Site.deleted_at.is_(None),
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site configuration not found",
        )

    site_dict = orm_to_config_dict(config)
    org_defaults = await _load_org_defaults(current_user.organisation_id, db)
    group_id = await _get_site_group_id(site_id, db)
    group_defaults = await _load_group_defaults(group_id, db) if group_id else None

    resolved = resolve_config(
        site_dict,
        org_defaults=org_defaults,
        group_defaults=group_defaults,
    )

    # For each config field, determine the source
    sources: dict[str, dict] = {}
    for field in CONFIG_FIELDS:
        site_val = site_dict.get(field)
        group_val = group_defaults.get(field) if group_defaults else None
        org_val = org_defaults.get(field) if org_defaults else None
        system_val = SYSTEM_DEFAULTS.get(field)

        # Determine effective source (highest priority non-None wins)
        if site_val is not None:
            source = "site"
        elif group_val is not None:
            source = "group"
        elif org_val is not None:
            source = "org"
        elif system_val is not None:
            source = "system"
        else:
            source = "system"

        sources[field] = {
            "resolved_value": resolved.get(field),
            "source": source,
            "site_value": site_val,
            "group_value": group_val,
            "org_value": org_val,
            "system_value": system_val,
        }

    return {
        "site_id": str(site_id),
        "site_group_id": str(group_id) if group_id else None,
        "fields": sources,
    }


@router.post("/sites/{site_id}/publish")
async def publish_config(
    site_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Publish fully-resolved site config to CDN. Requires admin role."""
    result = await db.execute(
        select(SiteConfig)
        .join(Site)
        .where(
            SiteConfig.site_id == site_id,
            Site.organisation_id == current_user.organisation_id,
            Site.deleted_at.is_(None),
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site configuration not found",
        )

    config_dict = orm_to_config_dict(config, include_id=True)
    org_defaults = await _load_org_defaults(current_user.organisation_id, db)
    group_id = await _get_site_group_id(site_id, db)
    group_defaults = await _load_group_defaults(group_id, db) if group_id else None
    resolved = resolve_config(
        config_dict,
        org_defaults=org_defaults,
        group_defaults=group_defaults,
    )

    # Allow extensions to enrich the published config (e.g. A/B test data)
    registry = get_registry()
    for enricher in registry.config_enrichers:
        await enricher(site_id, db, resolved)

    publish_result = await publish_site_config(str(site_id), resolved)

    if not publish_result.success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Publish failed: {publish_result.error}",
        )

    return {
        "published": True,
        "path": publish_result.path,
        "published_at": publish_result.published_at,
    }


# ── Helpers ──────────────────────────────────────────────────────────


async def _get_site_org_id(site_id: uuid.UUID, db: AsyncSession) -> uuid.UUID | None:
    """Look up the organisation_id for a site."""
    result = await db.execute(select(Site.organisation_id).where(Site.id == site_id))
    return result.scalar_one_or_none()


async def _get_site_group_id(site_id: uuid.UUID, db: AsyncSession) -> uuid.UUID | None:
    """Look up the site_group_id for a site."""
    result = await db.execute(select(Site.site_group_id).where(Site.id == site_id))
    return result.scalar_one_or_none()


async def _load_org_defaults(organisation_id: uuid.UUID, db: AsyncSession) -> dict | None:
    """Load the org-level config defaults, or None if not set."""
    result = await db.execute(select(OrgConfig).where(OrgConfig.organisation_id == organisation_id))
    org_config = result.scalar_one_or_none()
    if org_config is None:
        return None
    return orm_to_config_dict(org_config)


async def _load_group_defaults(group_id: uuid.UUID, db: AsyncSession) -> dict | None:
    """Load the site-group-level config defaults, or None if not set."""
    result = await db.execute(
        select(SiteGroupConfig).where(SiteGroupConfig.site_group_id == group_id)
    )
    group_config = result.scalar_one_or_none()
    if group_config is None:
        return None
    return orm_to_config_dict(group_config)
