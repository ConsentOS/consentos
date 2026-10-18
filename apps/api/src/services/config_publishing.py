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
from sqlalchemy.orm import aliased

from src.models.site import Site
from src.models.site_config_revision import SiteConfigRevision
from src.models.user import User
from src.services.config_snapshot import (
    SiteNotFoundError,
    build_site_snapshot,
    changed_sources,
)


class DraftOutOfDateError(Exception):
    """The draft changed after the publisher reviewed it."""


class NothingToPublishError(Exception):
    """The draft is identical to the live revision."""


class RevisionNotFoundError(LookupError):
    """The revision doesn't exist or belongs to another site."""


class AlreadyLiveError(Exception):
    """The revision to roll back to is already live."""


@dataclass(frozen=True)
class DraftStatus:
    live_revision: SiteConfigRevision | None
    content_hash: str
    has_unpublished_changes: bool
    changed_sources: list[dict[str, Any]]
    # What changed that visitors consented to, e.g. ``["categories"]``.
    # When non-empty the publish dialog pre-ticks "Ask visitors to
    # consent again".
    reconsent_reasons: list[str]


# What a visitor's consent covers, by where it sits in a snapshot. A
# change to any of these is reason to ask visitors again.
_CONSENT_SCOPE: dict[str, tuple[str, str | None]] = {
    "categories": ("config", "enabled_categories"),
    "purposes": ("category_tcf_purposes", None),
    "vendors": ("config", "disclosed_vendor_ids"),
}


def reconsent_reasons(live: dict[str, Any], draft: dict[str, Any]) -> list[str]:
    """Name what changed between two snapshots that visitors consented to."""

    def scoped(snapshot: dict[str, Any], section: str, key: str | None) -> Any:
        value = snapshot.get(section)
        return value.get(key) if key and isinstance(value, dict) else value

    return [
        reason
        for reason, (section, key) in _CONSENT_SCOPE.items()
        if scoped(live, section, key) != scoped(draft, section, key)
    ]


@dataclass(frozen=True)
class RevisionEntry:
    """A revision as History shows it."""

    revision: SiteConfigRevision
    is_live: bool
    published_by_name: str | None
    rolled_back_from_number: int | None


async def list_revisions(
    db: AsyncSession, site_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[RevisionEntry], int]:
    """A page of the site's revisions, newest first, and the total count."""
    total = (
        await db.execute(
            select(func.count())
            .select_from(SiteConfigRevision)
            .where(SiteConfigRevision.site_id == site_id)
        )
    ).scalar_one()
    rows = (
        await db.execute(
            _revision_entries(site_id)
            .order_by(SiteConfigRevision.number.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [_entry(*row) for row in rows], total


async def get_revision(
    db: AsyncSession, site_id: uuid.UUID, revision_id: uuid.UUID
) -> RevisionEntry | None:
    row = (
        await db.execute(_revision_entries(site_id).where(SiteConfigRevision.id == revision_id))
    ).first()
    return _entry(*row) if row else None


def _revision_entries(site_id: uuid.UUID):
    source = aliased(SiteConfigRevision)
    return (
        select(
            SiteConfigRevision,
            Site.live_revision_id,
            User.full_name,
            source.number,
        )
        .join(Site, Site.id == SiteConfigRevision.site_id)
        .outerjoin(User, User.id == SiteConfigRevision.published_by)
        .outerjoin(source, source.id == SiteConfigRevision.rolled_back_from_id)
        .where(SiteConfigRevision.site_id == site_id)
    )


def _entry(
    revision: SiteConfigRevision,
    live_revision_id: uuid.UUID | None,
    published_by_name: str | None,
    rolled_back_from_number: int | None,
) -> RevisionEntry:
    return RevisionEntry(
        revision=revision,
        is_live=revision.id == live_revision_id,
        published_by_name=published_by_name,
        rolled_back_from_number=rolled_back_from_number,
    )


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
            # Nobody has consented to a site that was never published.
            reconsent_reasons=[],
        )
    return DraftStatus(
        live_revision=live,
        content_hash=built.content_hash,
        has_unpublished_changes=built.content_hash != live.content_hash,
        changed_sources=changed_sources(live.sources, built.sources),
        reconsent_reasons=reconsent_reasons(live.snapshot, built.snapshot),
    )


async def publish_draft(
    db: AsyncSession,
    site_id: uuid.UUID,
    *,
    expected_content_hash: str,
    published_by: uuid.UUID | None,
    note: str | None = None,
    requires_reconsent: bool = False,
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
    site = await _lock_site(db, site_id)
    built = await build_site_snapshot(db, site_id)
    if built.content_hash != expected_content_hash:
        raise DraftOutOfDateError(built.content_hash)

    live = await _live_for_update(db, site)
    if live is not None and live.content_hash == built.content_hash:
        raise NothingToPublishError(str(site_id))

    return await _make_live(
        db,
        site,
        live,
        snapshot=built.snapshot,
        site_layer=built.site_layer,
        sources=built.sources,
        content_hash=built.content_hash,
        note=note,
        published_by=published_by,
        requires_reconsent=requires_reconsent,
    )


async def rollback_to_revision(
    db: AsyncSession,
    site_id: uuid.UUID,
    revision_id: uuid.UUID,
    *,
    published_by: uuid.UUID | None,
    requires_reconsent: bool = False,
) -> SiteConfigRevision:
    """Make an earlier revision live again by copying it into a new one.

    History only ever grows: the copy gets the next number and points
    back at its source. The draft is not touched, so any unpublished
    changes are kept and compared against the new live revision.

    Raises:
        SiteNotFoundError: the site doesn't exist or isn't active.
        RevisionNotFoundError: the revision isn't one of this site's.
        AlreadyLiveError: the revision is already live.
    """
    site = await _lock_site(db, site_id)
    source = await db.get(SiteConfigRevision, revision_id)
    if source is None or source.site_id != site_id:
        raise RevisionNotFoundError(str(revision_id))
    if source.id == site.live_revision_id:
        raise AlreadyLiveError(str(revision_id))

    return await _make_live(
        db,
        site,
        await _live_for_update(db, site),
        snapshot=source.snapshot,
        site_layer=source.site_layer,
        sources=source.sources,
        content_hash=source.content_hash,
        note=f"Rollback to v{source.number}",
        published_by=published_by,
        requires_reconsent=requires_reconsent,
        rolled_back_from_id=source.id,
    )


async def _lock_site(db: AsyncSession, site_id: uuid.UUID) -> Site:
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
    return site


async def _live_for_update(db: AsyncSession, site: Site) -> SiteConfigRevision | None:
    if site.live_revision_id is None:
        return None
    return await db.get(SiteConfigRevision, site.live_revision_id)


async def _make_live(
    db: AsyncSession,
    site: Site,
    live: SiteConfigRevision | None,
    *,
    snapshot: dict[str, Any],
    site_layer: dict[str, Any],
    sources: list[dict[str, Any]],
    content_hash: str,
    note: str | None,
    published_by: uuid.UUID | None,
    requires_reconsent: bool,
    rolled_back_from_id: uuid.UUID | None = None,
) -> SiteConfigRevision:
    """Add a revision with the next number and point the site at it.

    It keeps the live revision's consent version, so returning visitors
    aren't asked again, unless ``requires_reconsent`` gives it a new one.
    """
    revision = SiteConfigRevision(
        site_id=site.id,
        number=await _next_revision_number(db, site.id),
        consent_version=(live.consent_version if live and not requires_reconsent else uuid.uuid4()),
        requires_reconsent=requires_reconsent,
        snapshot=snapshot,
        site_layer=site_layer,
        sources=sources,
        content_hash=content_hash,
        note=note,
        rolled_back_from_id=rolled_back_from_id,
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
