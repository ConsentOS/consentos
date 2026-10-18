import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.cookie import Cookie, CookieCategory
from src.models.site import Site
from src.models.site_config import SiteConfig
from src.models.site_config_revision import SiteConfigRevision
from src.schemas.auth import CurrentUser
from src.schemas.cookie import ReviewStatus
from src.schemas.revision import DraftStatusResponse, PublishRequest, RevisionSummary
from src.schemas.site import SiteConfigResponse
from src.services.config_layers import (
    get_site_group_id,
    get_site_org_id,
    load_group_defaults,
    load_org_defaults,
)
from src.services.config_publishing import (
    DraftOutOfDateError,
    DraftStatus,
    NothingToPublishError,
    get_draft_status,
    get_live_revision,
    publish_draft,
)
from src.services.config_resolver import (
    CONFIG_FIELDS,
    orm_to_config_dict,
    resolve_config,
)
from src.services.config_snapshot import SiteNotFoundError, render_public_config
from src.services.dependencies import require_role
from src.services.geoip import detect_region

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/sites/{site_id}", response_model=SiteConfigResponse)
async def get_public_site_config(
    site_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Public endpoint: retrieve site config. No auth required.

    Returned values are cascade-resolved (system / org / group / site)
    so scalar fields are always concrete, even when the row has nulls
    from an operator clearing an override. The banner script itself
    uses ``/sites/{id}/geo-resolved`` for region-aware resolution; this
    endpoint exists for tooling that just wants the effective shape.
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

    org_id = await get_site_org_id(site_id, db)
    org_defaults = await load_org_defaults(org_id, db) if org_id else None
    group_id = await get_site_group_id(site_id, db)
    group_defaults = await load_group_defaults(group_id, db) if group_id else None
    resolved = resolve_config(
        orm_to_config_dict(config),
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


@router.get("/sites/{site_id}/resolved")
async def get_resolved_config(
    site_id: uuid.UUID,
    region: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Public endpoint: the live revision with ``region``'s blocking mode applied."""
    revision = await _require_live_revision(site_id, db)
    return render_public_config(
        revision.snapshot,
        site_id=site_id,
        consent_version=revision.consent_version,
        region=region,
    )


@router.get("/sites/{site_id}/geo-resolved")
async def get_geo_resolved_config(
    site_id: uuid.UUID,
    request: Request,
    locale: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Public endpoint: the live revision for the visitor's detected region.

    Serves the site's live revision, so saved but unpublished changes are
    not visible here. The region is detected from CDN headers or IP
    geolocation and its blocking mode applied.

    Pass ``?locale=`` to receive that locale's banner translation in the
    response (base-language fallback applies); omit it for none. The
    response therefore varies by site, country and locale.
    """
    revision = await _require_live_revision(site_id, db)
    geo = await detect_region(request)
    public = render_public_config(
        revision.snapshot,
        site_id=site_id,
        consent_version=revision.consent_version,
        region=geo.region,
        locale=locale,
    )
    public["detected_country"] = geo.country_code
    public["detected_region"] = geo.region
    return public


async def _require_live_revision(site_id: uuid.UUID, db: AsyncSession) -> SiteConfigRevision:
    revision = await get_live_revision(db, site_id)
    if revision is None:
        # Also covers sites that don't exist, so an unpublished site can't
        # be told apart from a missing one. The banner uses its built-in
        # defaults on any non-success response.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No published configuration for this site",
        )
    return revision


@router.get("/sites/{site_id}/cookies")
async def get_public_cookies(
    site_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Public endpoint: cookies grouped by category for the embedded widget.

    Returns the same shape the hosted-page template used to render server
    side, as JSON. Categories are filtered to those the site has enabled
    via the resolved cascade; cookies with no category fall under an
    explicit ``uncategorised`` bucket so operators can spot them.
    """
    site_result = await db.execute(
        select(Site).where(
            Site.id == site_id,
            Site.is_active.is_(True),
            Site.deleted_at.is_(None),
        )
    )
    site = site_result.scalar_one_or_none()
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found",
        )

    config_result = await db.execute(select(SiteConfig).where(SiteConfig.site_id == site_id))
    config = config_result.scalar_one_or_none()

    org_id = await get_site_org_id(site_id, db)
    org_defaults = await load_org_defaults(org_id, db) if org_id else None
    group_id = await get_site_group_id(site_id, db)
    group_defaults = await load_group_defaults(group_id, db) if group_id else None
    resolved = resolve_config(
        orm_to_config_dict(config) if config else {},
        org_defaults=org_defaults,
        group_defaults=group_defaults,
    )
    enabled_slugs = set(resolved.get("enabled_categories") or [])

    cat_result = await db.execute(select(CookieCategory).order_by(CookieCategory.display_order))
    all_categories = list(cat_result.scalars().all())

    cookie_result = await db.execute(
        select(Cookie).where(Cookie.site_id == site_id).order_by(Cookie.name)
    )
    cookies = list(cookie_result.scalars().all())

    by_cat_id: dict[uuid.UUID, list[Cookie]] = {}
    uncategorised: list[Cookie] = []
    for cookie in cookies:
        if cookie.review_status == ReviewStatus.rejected:
            continue
        if cookie.category_id:
            by_cat_id.setdefault(cookie.category_id, []).append(cookie)
        else:
            uncategorised.append(cookie)

    categories_out = []
    for cat in all_categories:
        if cat.slug not in enabled_slugs:
            continue
        categories_out.append(
            {
                "slug": cat.slug,
                "name": cat.name,
                "description": cat.description or "",
                "locked": cat.is_essential,
                "cookies": [_cookie_to_dict(c) for c in by_cat_id.get(cat.id, [])],
            }
        )

    if uncategorised:
        categories_out.append(
            {
                "slug": "uncategorised",
                "name": "Uncategorised",
                "description": ("Cookies that have not yet been assigned to a category."),
                "locked": False,
                "cookies": [_cookie_to_dict(c) for c in uncategorised],
            }
        )

    return {
        "site_id": str(site_id),
        "site_name": site.display_name or site.domain,
        "domain": site.domain,
        "privacy_policy_url": resolved.get("privacy_policy_url"),
        "consent_expiry_days": resolved.get("consent_expiry_days") or 365,
        "categories": categories_out,
    }


def _cookie_to_dict(cookie: Cookie) -> dict:
    return {
        "name": cookie.name,
        "domain": cookie.domain,
        "type": cookie.storage_type,
        "description": cookie.description or "",
        "vendor": cookie.vendor or "",
    }


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
    org_defaults = await load_org_defaults(current_user.organisation_id, db)
    group_id = await get_site_group_id(site_id, db)
    group_defaults = await load_group_defaults(group_id, db) if group_id else None

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


@router.get("/sites/{site_id}/draft", response_model=DraftStatusResponse)
async def get_draft(
    site_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> DraftStatus:
    """Whether the site has unpublished changes, and the hash to publish them."""
    await _require_org_site(site_id, current_user, db)
    return await get_draft_status(db, site_id)


@router.post("/sites/{site_id}/publish", response_model=RevisionSummary)
async def publish_config(
    site_id: uuid.UUID,
    body: PublishRequest,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> SiteConfigRevision:
    """Publish the site's draft as a new live revision. Requires admin role."""
    await _require_org_site(site_id, current_user, db)
    try:
        return await publish_draft(
            db,
            site_id,
            expected_content_hash=body.expected_content_hash,
            published_by=current_user.id,
            note=body.note,
            requires_reconsent=body.ask_visitors_again,
        )
    except SiteNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found") from exc
    except DraftOutOfDateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The draft has changed since you reviewed it. Review the changes again.",
        ) from exc
    except NothingToPublishError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="There are no unpublished changes",
        ) from exc


async def _require_org_site(
    site_id: uuid.UUID, current_user: CurrentUser, db: AsyncSession
) -> None:
    site_id_in_org = (
        await db.execute(
            select(Site.id).where(
                Site.id == site_id,
                Site.organisation_id == current_user.organisation_id,
                Site.is_active.is_(True),
                Site.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if site_id_in_org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
