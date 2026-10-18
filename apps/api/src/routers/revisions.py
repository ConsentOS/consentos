"""Draft, publish and revision history endpoints for a site's config."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.site import Site
from src.models.site_config_revision import SiteConfigRevision
from src.schemas.auth import CurrentUser
from src.schemas.revision import (
    DraftStatusResponse,
    PublishRequest,
    RevisionDetail,
    RevisionList,
    RevisionSummary,
    RollbackRequest,
)
from src.services.config_publishing import (
    AlreadyLiveError,
    DraftOutOfDateError,
    DraftStatus,
    NothingToPublishError,
    RevisionEntry,
    RevisionNotFoundError,
    get_draft_status,
    get_live_revision,
    get_revision,
    list_revisions,
    publish_draft,
    reconsent_reasons,
    rollback_to_revision,
)
from src.services.config_snapshot import SiteNotFoundError
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
    try:
        return await rollback_to_revision(
            db,
            site_id,
            revision_id,
            published_by=current_user.id,
            requires_reconsent=body.ask_visitors_again,
        )
    except SiteNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found") from exc
    except RevisionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found"
        ) from exc
    except AlreadyLiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="That revision is already live"
        ) from exc


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
