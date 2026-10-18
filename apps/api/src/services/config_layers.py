"""Loaders for the inputs that make up a site's effective config.

Shared by the config endpoints and the revision snapshot builder so both
read the cascade layers and supporting data the same way.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.cookie import CookieAllowListEntry, CookieCategory
from src.models.iab_gvl import IabGvlMeta
from src.models.org_config import OrgConfig
from src.models.site import Site
from src.models.site_group import SiteGroup
from src.models.site_group_config import SiteGroupConfig
from src.services.config_resolver import orm_to_config_dict


async def get_site_org_id(site_id: uuid.UUID, db: AsyncSession) -> uuid.UUID | None:
    """Look up the organisation_id for a site."""
    result = await db.execute(select(Site.organisation_id).where(Site.id == site_id))
    return result.scalar_one_or_none()


async def get_site_group_id(site_id: uuid.UUID, db: AsyncSession) -> uuid.UUID | None:
    """Look up the site_group_id for a site, ignoring groups from another organisation."""
    result = await db.execute(
        select(Site.site_group_id)
        .join(SiteGroup, SiteGroup.id == Site.site_group_id)
        .where(Site.id == site_id, SiteGroup.organisation_id == Site.organisation_id)
    )
    return result.scalar_one_or_none()


async def load_org_defaults(organisation_id: uuid.UUID, db: AsyncSession) -> dict | None:
    """Load the org-level config defaults, or None if not set."""
    result = await db.execute(select(OrgConfig).where(OrgConfig.organisation_id == organisation_id))
    org_config = result.scalar_one_or_none()
    if org_config is None:
        return None
    return orm_to_config_dict(org_config)


async def load_group_defaults(group_id: uuid.UUID, db: AsyncSession) -> dict | None:
    """Load the site-group-level config defaults, or None if not set."""
    result = await db.execute(
        select(SiteGroupConfig).where(SiteGroupConfig.site_group_id == group_id)
    )
    group_config = result.scalar_one_or_none()
    if group_config is None:
        return None
    return orm_to_config_dict(group_config)


async def load_gvl_version(db: AsyncSession) -> int | None:
    """Return the currently-cached IAB GVL version, or ``None`` if unsynced.

    Surfaced into the public config so the banner can stamp it onto
    generated TC strings (``vendorListVersion`` field).
    """
    result = await db.execute(select(IabGvlMeta.vendor_list_version).limit(1))
    return result.scalar_one_or_none()


async def load_cookie_count(db: AsyncSession, site_id: uuid.UUID) -> int:
    """Return the number of allow-listed cookies for the site.

    Surfaced into the public config so the banner can render the optional
    "N cookies used on this site" line when ``showCookieCount`` is enabled.
    """
    result = await db.execute(
        select(func.count())
        .select_from(CookieAllowListEntry)
        .where(CookieAllowListEntry.site_id == site_id)
    )
    return int(result.scalar_one() or 0)


async def load_category_tcf_purposes(db: AsyncSession) -> dict[str, list[int]]:
    """Return the cookie-category slug → TCF purpose IDs mapping.

    The banner uses this to translate accepted cookie categories into
    TCF purpose IDs when building TCData. Categories without a mapping
    are omitted from the result.
    """
    result = await db.execute(
        select(CookieCategory.slug, CookieCategory.tcf_purpose_ids).where(
            CookieCategory.tcf_purpose_ids.isnot(None)
        )
    )
    return {slug: ids for slug, ids in result.all() if ids}
