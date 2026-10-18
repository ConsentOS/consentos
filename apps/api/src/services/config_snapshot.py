"""Build the frozen snapshot a site revision stores.

A snapshot is everything the banner needs, resolved through the whole
cascade with parent values baked in, so a revision always serves exactly
what it served when it was published. The region is not applied here:
``regional_modes`` is kept in the snapshot and applied per request by
``render_public_config``.

Alongside the snapshot, the builder records:

- ``site_layer``: the site's own values, so a draft can be discarded by
  restoring them.
- ``sources``: the parent layers the snapshot was built from, each with
  a hash, so the admin UI can tell when a parent has changed since.
- ``content_hash``: a hash of the snapshot, used to tell whether the
  current draft differs from a revision.
"""

from __future__ import annotations

import datetime
import decimal
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.extensions.registry import get_registry
from src.models.cookie import Cookie, CookieAllowListEntry, CookieCategory
from src.models.site import Site
from src.models.site_config import SiteConfig
from src.models.translation import Translation
from src.schemas.cookie import ReviewStatus
from src.services.config_layers import (
    get_site_group_id,
    load_category_tcf_purposes,
    load_cookie_count,
    load_group_defaults,
    load_gvl_version,
    load_org_defaults,
)
from src.services.config_resolver import (
    CONFIG_FIELDS,
    apply_consent_group,
    apply_region,
    build_public_config,
    orm_to_config_dict,
    resolve_config,
)

# Bumped if the snapshot layout changes, so older revisions can still be
# read correctly.
SNAPSHOT_FORMAT = 1

# Fields the resolver carries that don't affect what the banner serves.
# Leaving them out stops a scan-setting change from looking like an
# unpublished config change.
_UNSERVED_FIELDS = frozenset({"id", "scan_max_pages", "scan_schedule_cron"})


class SiteNotFoundError(LookupError):
    """The site doesn't exist, is inactive or has been deleted."""


@dataclass(frozen=True)
class SiteSnapshot:
    snapshot: dict[str, Any]
    site_layer: dict[str, Any]
    sources: list[dict[str, Any]]
    content_hash: str


async def build_site_snapshot(db: AsyncSession, site_id: uuid.UUID) -> SiteSnapshot:
    """Resolve and freeze everything the site currently serves."""
    site = await _load_active_site(db, site_id)
    site_config = (
        await db.execute(select(SiteConfig).where(SiteConfig.site_id == site_id))
    ).scalar_one_or_none()

    org_defaults = await load_org_defaults(site.organisation_id, db)
    group_id = await get_site_group_id(site_id, db)
    group_defaults = await load_group_defaults(group_id, db) if group_id else None

    resolved = resolve_config(
        orm_to_config_dict(site_config) if site_config else {},
        org_defaults=org_defaults,
        group_defaults=group_defaults,
    )
    apply_consent_group(resolved, group_id)
    config = {key: value for key, value in resolved.items() if key not in _UNSERVED_FIELDS}

    translations = await _load_translations(db, site_id)
    snapshot = to_json(
        {
            "format": SNAPSHOT_FORMAT,
            "config": config,
            "extensions": await _run_enrichers(db, site_id, config),
            "gvl_version": await load_gvl_version(db),
            "category_tcf_purposes": await load_category_tcf_purposes(db),
            "cookie_count": await load_cookie_count(db, site_id),
            "translations": {locale.lower(): strings for locale, strings in translations},
            "cookies": await _load_declared_cookies(db, site_id),
        }
    )

    site_layer = to_json(
        {
            "format": SNAPSHOT_FORMAT,
            "site_config": _site_config_values(site_config),
            "translations": dict(translations),
            "cookies": await _load_cookie_classifications(db, site_id),
            "allow_list": await _load_allow_list(db, site_id),
        }
    )

    sources = [
        {
            "kind": "organisation_config",
            "id": str(site.organisation_id),
            "content_hash": content_hash(org_defaults or {}),
        }
    ]
    if group_id:
        sources.append(
            {
                "kind": "site_group_config",
                "id": str(group_id),
                "content_hash": content_hash(group_defaults or {}),
            }
        )

    return SiteSnapshot(
        snapshot=snapshot,
        site_layer=site_layer,
        sources=to_json(sources),
        content_hash=content_hash(snapshot),
    )


def render_public_config(
    snapshot: dict[str, Any],
    *,
    site_id: uuid.UUID | str,
    consent_version: uuid.UUID | str,
    region: str | None = None,
    locale: str | None = None,
) -> dict[str, Any]:
    """Turn a stored snapshot into the payload the banner receives.

    ``consent_version`` becomes ``id``, which the banner compares with
    the version stored alongside a visitor's consent to decide whether
    to ask again.
    """
    config = {**snapshot["config"], "id": str(consent_version)}
    if region:
        config = apply_region(config, region)
    public = build_public_config(
        str(site_id),
        config,
        gvl_version=snapshot.get("gvl_version"),
        category_tcf_purposes=snapshot.get("category_tcf_purposes"),
        cookie_count=snapshot.get("cookie_count", 0),
    )
    public.update(snapshot.get("extensions") or {})
    public["translations"] = select_translation(snapshot.get("translations") or {}, locale)
    return public


def select_translation(
    translations: dict[str, dict[str, str]], locale: str | None
) -> dict[str, dict[str, str]]:
    """Pick one locale's strings, falling back to the base language.

    Returns ``{requested_locale: strings}`` so the banner's lookup hits
    however the match was made, or ``{}`` so it uses its built-in text.
    """
    if not locale:
        return {}
    requested = locale.lower()
    base = requested.split("-")[0]
    for candidate in (requested, base):
        if candidate in translations:
            return {requested: translations[candidate]}
    return {}


def changed_sources(
    recorded: list[dict[str, Any]], current: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return the current parent layers that differ from those recorded.

    A parent counts as changed when its content differs, or when the site
    now has a parent it didn't have before. A parent that has gone away
    shows up as the recorded entry, so the caller can say what was lost.
    """
    recorded_by_key = {(s["kind"], s["id"]): s for s in recorded}
    current_by_key = {(s["kind"], s["id"]): s for s in current}
    changed = [
        source
        for key, source in current_by_key.items()
        if recorded_by_key.get(key, {}).get("content_hash") != source["content_hash"]
    ]
    changed.extend(source for key, source in recorded_by_key.items() if key not in current_by_key)
    return changed


def content_hash(value: Any) -> str:
    """SHA-256 of a value's canonical JSON form."""
    canonical = json.dumps(to_json(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def to_json(value: Any) -> Any:
    """Convert a value to plain JSON types, as JSONB will store it.

    Hashing the converted value means a snapshot hashes the same before
    it is stored and after it is read back.
    """
    return json.loads(json.dumps(value, default=_json_default))


def _json_default(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime.datetime | datetime.date):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    raise TypeError(f"Cannot store {type(value).__name__} in a config snapshot")


async def _load_active_site(db: AsyncSession, site_id: uuid.UUID) -> Site:
    site = (
        await db.execute(
            select(Site).where(
                Site.id == site_id,
                Site.is_active.is_(True),
                Site.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if site is None:
        raise SiteNotFoundError(str(site_id))
    return site


async def _run_enrichers(
    db: AsyncSession, site_id: uuid.UUID, config: dict[str, Any]
) -> dict[str, Any]:
    """Run registered enrichers and return only what they added or changed.

    Enrichers mutate the config they are given. Running them on a copy
    and keeping the difference lets the served payload include their
    output without it being mixed into the resolved config.
    """
    enriched = {**config}
    for enricher in get_registry().config_enrichers:
        await enricher(site_id, db, enriched)
    return {
        key: value for key, value in enriched.items() if key not in config or config[key] != value
    }


async def _load_translations(
    db: AsyncSession, site_id: uuid.UUID
) -> list[tuple[str, dict[str, str]]]:
    result = await db.execute(
        select(Translation.locale, Translation.strings)
        .where(Translation.site_id == site_id)
        .order_by(Translation.locale)
    )
    return [(locale, strings) for locale, strings in result.all()]


async def _load_declared_cookies(db: AsyncSession, site_id: uuid.UUID) -> list[dict[str, Any]]:
    """Cookies the site declares to visitors: everything not rejected.

    Matches what the public cookie list shows today. Only fields an
    operator sets are included, so a rescan that only updates
    ``last_seen_at`` doesn't look like an unpublished change.
    """
    result = await db.execute(
        select(Cookie, CookieCategory.slug)
        .outerjoin(CookieCategory, CookieCategory.id == Cookie.category_id)
        .where(Cookie.site_id == site_id, Cookie.review_status != ReviewStatus.rejected)
        .order_by(Cookie.name, Cookie.domain, Cookie.storage_type)
    )
    return [
        {
            "name": cookie.name,
            "domain": cookie.domain,
            "type": cookie.storage_type,
            "description": cookie.description or "",
            "vendor": cookie.vendor or "",
            "category": category_slug,
        }
        for cookie, category_slug in result.all()
    ]


async def _load_cookie_classifications(
    db: AsyncSession, site_id: uuid.UUID
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(Cookie.id, Cookie.category_id, Cookie.review_status)
        .where(Cookie.site_id == site_id)
        .order_by(Cookie.id)
    )
    return [
        {"id": cookie_id, "category_id": category_id, "review_status": review_status}
        for cookie_id, category_id, review_status in result.all()
    ]


async def _load_allow_list(db: AsyncSession, site_id: uuid.UUID) -> list[dict[str, Any]]:
    result = await db.execute(
        select(CookieAllowListEntry)
        .where(CookieAllowListEntry.site_id == site_id)
        .order_by(CookieAllowListEntry.name_pattern, CookieAllowListEntry.domain_pattern)
    )
    return [
        {
            "category_id": entry.category_id,
            "name_pattern": entry.name_pattern,
            "domain_pattern": entry.domain_pattern,
            "description": entry.description,
        }
        for entry in result.scalars().all()
    ]


def _site_config_values(site_config: SiteConfig | None) -> dict[str, Any]:
    """The site's own cascade values, with ``None`` meaning "inherit".

    Unlike ``orm_to_config_dict`` this keeps the ``None`` values, because
    restoring a draft has to clear overrides added since publish.
    """
    if site_config is None:
        return {}
    return {
        field: getattr(site_config, field) for field in CONFIG_FIELDS if hasattr(site_config, field)
    }
