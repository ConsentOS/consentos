import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.extensions.registry import get_registry
from src.models.consent import ConsentRecord
from src.models.site import Site
from src.schemas.auth import CurrentUser
from src.schemas.consent import (
    ConsentRecordCreate,
    ConsentRecordListResponse,
    ConsentRecordResponse,
    ConsentVerifyResponse,
)
from src.services.dependencies import require_role
from src.services.pseudonymisation import pseudonymise

router = APIRouter(prefix="/consent", tags=["consent"])


@router.post("/", response_model=ConsentRecordResponse, status_code=status.HTTP_201_CREATED)
async def record_consent(
    body: ConsentRecordCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ConsentRecord:
    """Record a consent event from the banner. Public endpoint (no auth required)."""
    # Pseudonymise IP and user agent with HMAC so the resulting values
    # cannot be reversed without the server-side secret.
    client_ip = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")

    record = ConsentRecord(
        site_id=body.site_id,
        visitor_id=body.visitor_id,
        ip_hash=pseudonymise(client_ip),
        user_agent_hash=pseudonymise(user_agent),
        action=body.action,
        categories_accepted=body.categories_accepted,
        categories_rejected=body.categories_rejected,
        tc_string=body.tc_string,
        gcm_state=body.gcm_state,
        page_url=body.page_url,
        country_code=body.country_code,
        region_code=body.region_code,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)

    # Invoke any registered post-record hooks (EE consent receipts, etc.)
    for hook in get_registry().consent_record_hooks:
        await hook(db, record)

    return record


async def _load_record_for_org(
    consent_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession,
) -> ConsentRecord:
    """Load a consent record and enforce tenant isolation.

    The record's site must belong to the caller's organisation. A record
    from another tenant returns 404 rather than 403 so we don't leak
    existence across tenants.
    """
    stmt = (
        select(ConsentRecord)
        .join(Site, Site.id == ConsentRecord.site_id)
        .where(
            ConsentRecord.id == consent_id,
            Site.organisation_id == current_user.organisation_id,
            Site.deleted_at.is_(None),
        )
    )
    record = (await db.execute(stmt)).scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Consent record not found",
        )
    return record


@router.get("/", response_model=ConsentRecordListResponse)
async def list_consent_records(
    site_id: uuid.UUID = Query(..., description="Filter by site"),
    visitor_id: str | None = Query(None, description="Filter by visitor ID (exact match)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List consent records for a site, with optional visitor_id filter.

    Tenant-isolated — the site must belong to the caller's organisation.
    Returns newest records first.
    """
    # Verify site belongs to the caller's org.
    site = (
        await db.execute(
            select(Site).where(
                Site.id == site_id,
                Site.organisation_id == current_user.organisation_id,
                Site.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")

    base = select(ConsentRecord).where(ConsentRecord.site_id == site_id)
    count_base = (
        select(func.count()).select_from(ConsentRecord).where(ConsentRecord.site_id == site_id)
    )

    if visitor_id:
        base = base.where(ConsentRecord.visitor_id == visitor_id)
        count_base = count_base.where(ConsentRecord.visitor_id == visitor_id)

    total = await db.scalar(count_base) or 0
    items = (
        (
            await db.execute(
                base.order_by(ConsentRecord.consented_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    return {
        "items": list(items),
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{consent_id}", response_model=ConsentRecordResponse)
async def get_consent(
    consent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> ConsentRecord:
    """Retrieve a consent record by ID.

    Requires authentication and tenant membership. Consent records
    contain PII-adjacent data (hashed IP, page URL, category decisions)
    and must not be readable by anyone holding a record UUID.
    """
    return await _load_record_for_org(consent_id, current_user, db)


@router.get("/verify/{consent_id}", response_model=ConsentVerifyResponse)
async def verify_consent(
    consent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "editor", "viewer")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verify that a consent record exists (audit proof).

    Same tenant-scoped auth as :func:`get_consent` — proof of consent
    is only meaningful to the organisation that owns the site, and
    leaking existence to arbitrary callers enables enumeration.
    """
    record = await _load_record_for_org(consent_id, current_user, db)
    return {
        "id": record.id,
        "site_id": record.site_id,
        "visitor_id": record.visitor_id,
        "action": record.action,
        "categories_accepted": record.categories_accepted,
        "consented_at": record.consented_at,
        "valid": True,
    }
