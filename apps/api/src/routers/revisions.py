"""Draft, publish and revision history endpoints for a site's config."""

import uuid
from collections.abc import Awaitable, Callable
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.site import Site
from src.models.site_config_revision import SiteConfigRevision
from src.models.site_group import SiteGroup
from src.schemas.auth import CurrentUser
from src.schemas.revision import (
    AffectedSiteResponse,
    BulkPublishRequest,
    BulkPublishResponse,
    DiffResponse,
    DraftStatusResponse,
    PreviewLink,
    PublishRequest,
    RevisionDetail,
    RevisionList,
    RevisionSummary,
    RollbackRequest,
)
from src.services.config_diff import EMPTY, Version, diff_versions
from src.services.config_preview import create_preview_token
from src.services.config_publishing import (
    AffectedSite,
    DraftStatus,
    PublishError,
    RevisionEntry,
    RevisionNotFoundError,
    bulk_publish,
    discard_draft,
    get_draft_status,
    get_live_revision,
    get_revision,
    list_affected_sites,
    list_revisions,
    publish_draft,
    reconsent_reasons,
    record_attempt,
    rollback_to_revision,
)
from src.services.config_snapshot import SiteNotFoundError, build_site_snapshot
from src.services.dependencies import require_role

router = APIRouter(prefix="/config", tags=["revisions"])

_ANY_ROLE = require_role("owner", "admin", "editor", "viewer")


@router.get("/sites/{site_id}/draft", response_model=DraftStatusResponse)
async def get_draft(
    site_id: uuid.UUID,
    current_user: CurrentUser = Depends(_ANY_ROLE),
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
    return await _attempt(
        db,
        site_id,
        "publish",
        current_user,
        lambda: publish_draft(
            db,
            site_id,
            expected_content_hash=body.expected_content_hash,
            published_by=current_user.id,
            note=body.note,
            requires_reconsent=body.ask_visitors_again,
        ),
    )


@router.post("/sites/{site_id}/discard", response_model=DraftStatusResponse)
async def discard(
    site_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> DraftStatus:
    """Put the site's own values back to the live revision. Requires admin role.

    Returns the draft status afterwards, which still shows unpublished
    changes if inherited defaults have changed.
    """
    await _require_org_site(site_id, current_user, db)
    try:
        await discard_draft(db, site_id)
    except SiteNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found") from exc
    except PublishError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message) from exc
    return await get_draft_status(db, site_id)


@router.get("/affected-sites", response_model=list[AffectedSiteResponse])
async def get_affected_sites(
    site_group_id: uuid.UUID | None = None,
    current_user: CurrentUser = Depends(_ANY_ROLE),
    db: AsyncSession = Depends(get_db),
) -> list[AffectedSite]:
    """Published sites with unpublished changes, across the organisation or one group."""
    if site_group_id is not None:
        group = await db.get(SiteGroup, site_group_id)
        if group is None or group.organisation_id != current_user.organisation_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Site group not found"
            )
    return await list_affected_sites(db, current_user.organisation_id, site_group_id=site_group_id)


@router.post("/bulk-publish", response_model=BulkPublishResponse)
async def bulk_publish_sites(
    body: BulkPublishRequest,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Publish several sites, each as its own revision. Requires admin role.

    One site failing doesn't stop the others; the response gives each
    site's revision number or the reason it failed.
    """
    batch_id, results = await bulk_publish(
        db,
        current_user.organisation_id,
        [(item.site_id, item.expected_content_hash) for item in body.sites],
        published_by=current_user.id,
        note=body.note,
        requires_reconsent=body.ask_visitors_again,
    )
    return {"batch_id": batch_id, "results": results}


@router.post("/sites/{site_id}/preview", response_model=PreviewLink)
async def create_preview_link(
    site_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """A short-lived link that shows the draft on the real site. Requires admin role.

    Only someone holding the link sees the draft; visitors keep getting
    the live revision.
    """
    await _require_org_site(site_id, current_user, db)
    site = await db.get(Site, site_id)
    token, expires_at = create_preview_token(site_id)
    return {
        "token": token,
        "expires_at": expires_at,
        "url": f"https://{site.domain}/?{urlencode({'consentos_preview': token})}",
    }


@router.get("/sites/{site_id}/revisions", response_model=RevisionList)
async def get_revisions(
    site_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(_ANY_ROLE),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The site's published revisions, newest first.

    Revisions can't be changed or deleted, so there are no write routes
    here other than publishing a new one.
    """
    await _require_org_site(site_id, current_user, db)
    entries, total = await list_revisions(db, site_id, limit=limit, offset=offset)
    return {"items": [_entry_dict(entry) for entry in entries], "total": total}


@router.get("/sites/{site_id}/revisions/{revision_id}", response_model=RevisionDetail)
async def get_revision_detail(
    site_id: uuid.UUID,
    revision_id: uuid.UUID,
    current_user: CurrentUser = Depends(_ANY_ROLE),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """One revision, including the snapshot it serves."""
    await _require_org_site(site_id, current_user, db)
    entry = await get_revision(db, site_id, revision_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found")
    live = await get_live_revision(db, site_id)
    return {
        **_entry_dict(entry),
        "snapshot": entry.revision.snapshot,
        "sources": entry.revision.sources,
        "rollback_reconsent_reasons": (
            reconsent_reasons(live.snapshot, entry.revision.snapshot) if live else []
        ),
    }


@router.get("/sites/{site_id}/diff", response_model=DiffResponse, response_model_by_alias=True)
async def get_diff(
    site_id: uuid.UUID,
    from_revision: uuid.UUID | None = None,
    to_revision: uuid.UUID | None = None,
    current_user: CurrentUser = Depends(_ANY_ROLE),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """What changed between two versions of the site's config.

    ``from_revision`` defaults to the live revision and ``to_revision``
    to the current draft, so with neither this is what a publish would
    change. ``to.content_hash`` is the hash to publish exactly what was
    compared.
    """
    await _require_org_site(site_id, current_user, db)
    before = (
        await _revision_or_404(db, site_id, from_revision)
        if from_revision
        else await get_live_revision(db, site_id)
    )
    if to_revision:
        after = await _revision_or_404(db, site_id, to_revision)
        after_version = _version(after)
        to_side = _side(after)
    else:
        built = await build_site_snapshot(db, site_id)
        after_version = Version(built.snapshot, built.site_layer, built.sources)
        to_side = {"revision_id": None, "number": None, "content_hash": built.content_hash}

    before_version = _version(before) if before else EMPTY
    return {
        "from": _side(before) if before else None,
        "to": to_side,
        "changes": diff_versions(before_version, after_version),
        "reconsent_reasons": (
            reconsent_reasons(before_version.snapshot, after_version.snapshot) if before else []
        ),
    }


async def _revision_or_404(
    db: AsyncSession, site_id: uuid.UUID, revision_id: uuid.UUID
) -> SiteConfigRevision:
    entry = await get_revision(db, site_id, revision_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found")
    return entry.revision


def _version(revision: SiteConfigRevision) -> Version:
    return Version(revision.snapshot, revision.site_layer, revision.sources)


def _side(revision: SiteConfigRevision) -> dict:
    return {
        "revision_id": revision.id,
        "number": revision.number,
        "content_hash": revision.content_hash,
    }


@router.post("/sites/{site_id}/revisions/{revision_id}/rollback", response_model=RevisionSummary)
async def rollback(
    site_id: uuid.UUID,
    revision_id: uuid.UUID,
    body: RollbackRequest,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> SiteConfigRevision:
    """Make an earlier revision live again as a new revision. Requires admin role.

    The draft is left as it is.
    """
    await _require_org_site(site_id, current_user, db)
    return await _attempt(
        db,
        site_id,
        "rollback",
        current_user,
        lambda: rollback_to_revision(
            db,
            site_id,
            revision_id,
            published_by=current_user.id,
            requires_reconsent=body.ask_visitors_again,
        ),
    )


# Refusals map to 409 unless listed here.
_ERROR_STATUS = {RevisionNotFoundError.code: status.HTTP_404_NOT_FOUND}


async def _attempt(
    db: AsyncSession,
    site_id: uuid.UUID,
    action: str,
    current_user: CurrentUser,
    operation: Callable[[], Awaitable[SiteConfigRevision]],
) -> SiteConfigRevision:
    """Run a publish or rollback and log the attempt, whatever the outcome.

    A failure rolls back everything the operation did, so the live
    revision and the draft are untouched, then logs the failure in its
    own commit so it survives the error response.
    """
    try:
        revision = await operation()
    except SiteNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found") from exc
    except PublishError as exc:
        await _record_failure(db, site_id, action, current_user, exc)
        raise HTTPException(
            status_code=_ERROR_STATUS.get(exc.code, status.HTTP_409_CONFLICT),
            detail=exc.message,
        ) from exc
    except Exception:
        await _record_failure(db, site_id, action, current_user, PublishError())
        raise
    await record_attempt(
        db, site_id, action=action, attempted_by=current_user.id, revision=revision
    )
    return revision


async def _record_failure(
    db: AsyncSession,
    site_id: uuid.UUID,
    action: str,
    current_user: CurrentUser,
    error: PublishError,
) -> None:
    await db.rollback()
    await record_attempt(db, site_id, action=action, attempted_by=current_user.id, error=error)
    await db.commit()


def _entry_dict(entry: RevisionEntry) -> dict:
    revision = entry.revision
    return {
        "id": revision.id,
        "number": revision.number,
        "content_hash": revision.content_hash,
        "consent_version": revision.consent_version,
        "requires_reconsent": revision.requires_reconsent,
        "note": revision.note,
        "published_by": revision.published_by,
        "published_at": revision.published_at,
        "is_live": entry.is_live,
        "published_by_name": entry.published_by_name,
        "rolled_back_from_id": revision.rolled_back_from_id,
        "rolled_back_from_number": entry.rolled_back_from_number,
    }


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
