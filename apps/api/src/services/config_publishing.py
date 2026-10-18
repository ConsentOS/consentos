"""Draft, publish and live revision lifecycle.

The existing config tables are the draft: every save still writes to
them, and nothing a visitor sees changes until the draft is published.
Publishing freezes the draft into a new ``SiteConfigRevision`` and makes
it the site's live revision, which is what the banner is served.

A draft has unpublished changes when the snapshot a publish would
produce now hashes differently from the live revision's snapshot. That
covers inherited organisation and site group changes as well as the
site's own.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.site import Site
from src.models.site_config_revision import SiteConfigRevision
from src.services.config_snapshot import (
    SiteNotFoundError,
    build_site_snapshot,
    changed_sources,
)


class DraftOutOfDateError(Exception):
    """The draft changed after the publisher reviewed it."""


class NothingToPublishError(Exception):
    """The draft is identical to the live revision."""


@dataclass(frozen=True)
class DraftStatus:
    live_revision: SiteConfigRevision | None
    content_hash: str
    has_unpublished_changes: bool
    changed_sources: list[dict[str, Any]]


async def get_live_revision(db: AsyncSession, site_id: uuid.UUID) -> SiteConfigRevision | None:
    """Return the revision an active site serves, or ``None`` if unpublished."""
    result = await db.execute(
        select(SiteConfigRevision)
        .join(Site, Site.live_revision_id == SiteConfigRevision.id)
        .where(
            Site.id == site_id,
            Site.is_active.is_(True),
            Site.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def get_draft_status(db: AsyncSession, site_id: uuid.UUID) -> DraftStatus:
    """Compare the current draft with the live revision."""
    built = await build_site_snapshot(db, site_id)
    live = await get_live_revision(db, site_id)
    if live is None:
        return DraftStatus(
            live_revision=None,
            content_hash=built.content_hash,
            has_unpublished_changes=True,
            changed_sources=[],
        )
    return DraftStatus(
        live_revision=live,
        content_hash=built.content_hash,
        has_unpublished_changes=built.content_hash != live.content_hash,
        changed_sources=changed_sources(live.sources, built.sources),
    )


async def publish_draft(
    db: AsyncSession,
    site_id: uuid.UUID,
    *,
    expected_content_hash: str,
    published_by: uuid.UUID | None,
    note: str | None = None,
) -> SiteConfigRevision:
    """Freeze the current draft into a new live revision.

    ``expected_content_hash`` is the draft hash the publisher reviewed.
    If the draft has changed since, the publish is refused so nobody
    publishes changes they haven't seen.

    Raises:
        SiteNotFoundError: the site doesn't exist or isn't active.
        DraftOutOfDateError: the draft no longer matches what was reviewed.
        NothingToPublishError: the draft matches the live revision.
    """
    # Locking the site row serialises publishes per site, so two at once
    # can't both read the same previous revision and take one number.
    site = (
        await db.execute(
            select(Site)
            .where(
                Site.id == site_id,
                Site.is_active.is_(True),
                Site.deleted_at.is_(None),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if site is None:
        raise SiteNotFoundError(str(site_id))

    built = await build_site_snapshot(db, site_id)
    if built.content_hash != expected_content_hash:
        raise DraftOutOfDateError(built.content_hash)

    live = (
        await db.get(SiteConfigRevision, site.live_revision_id) if site.live_revision_id else None
    )
    if live is not None and live.content_hash == built.content_hash:
        raise NothingToPublishError(str(site_id))

    revision = SiteConfigRevision(
        site_id=site_id,
        number=await _next_revision_number(db, site_id),
        consent_version=live.consent_version if live else uuid.uuid4(),
        snapshot=built.snapshot,
        site_layer=built.site_layer,
        sources=built.sources,
        content_hash=built.content_hash,
        note=note,
        published_by=published_by,
    )
    db.add(revision)
    await db.flush()
    site.live_revision_id = revision.id
    await db.flush()
    return revision


async def _next_revision_number(db: AsyncSession, site_id: uuid.UUID) -> int:
    highest = (
        await db.execute(
            select(func.max(SiteConfigRevision.number)).where(SiteConfigRevision.site_id == site_id)
        )
    ).scalar_one()
    return (highest or 0) + 1
