"""Compliance checking endpoints.

Evaluates a site's configuration against regulatory frameworks (GDPR, CNIL,
CCPA, ePrivacy, LGPD) and returns per-framework compliance reports with scores,
issues, and recommendations.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.models.cookie import Cookie
from src.models.site import Site
from src.models.site_config import SiteConfig
from src.schemas.compliance import (
    ComplianceCheckRequest,
    ComplianceCheckResponse,
    Framework,
)
from src.services.compliance import (
    SiteContext,
    calculate_overall_score,
    run_compliance_check,
)
from src.services.dependencies import get_org_site

router = APIRouter(prefix="/compliance", tags=["compliance"])


async def _build_site_context(
    site_id: uuid.UUID,
    db: AsyncSession,
) -> SiteContext:
    """Load site config and cookie stats to build a SiteContext."""
    # Fetch site config
    result = await db.execute(select(SiteConfig).where(SiteConfig.site_id == site_id))
    config = result.scalar_one_or_none()

    # Fetch cookie statistics
    total_q = await db.execute(
        select(func.count()).select_from(Cookie).where(Cookie.site_id == site_id)
    )
    total_cookies = total_q.scalar() or 0

    uncat_q = await db.execute(
        select(func.count())
        .select_from(Cookie)
        .where(
            Cookie.site_id == site_id,
            Cookie.category_id.is_(None),
        )
    )
    uncategorised_cookies = uncat_q.scalar() or 0

    if config is None:
        return SiteContext(
            total_cookies=total_cookies,
            uncategorised_cookies=uncategorised_cookies,
        )

    banner_config = config.banner_config or {}
    return SiteContext(
        blocking_mode=config.blocking_mode,
        regional_modes=config.regional_modes,
        tcf_enabled=config.tcf_enabled,
        gcm_enabled=config.gcm_enabled,
        consent_expiry_days=config.consent_expiry_days,
        privacy_policy_url=config.privacy_policy_url,
        banner_config=config.banner_config,
        total_cookies=total_cookies,
        uncategorised_cookies=uncategorised_cookies,
        has_reject_button=banner_config.get("show_reject_all", True),
        has_granular_choices=banner_config.get("show_category_toggles", True),
        has_cookie_wall=banner_config.get("cookie_wall", False),
        pre_ticked_boxes=banner_config.get("pre_ticked", False),
    )


@router.post(
    "/check/{site_id}",
    response_model=ComplianceCheckResponse,
    status_code=status.HTTP_200_OK,
)
async def check_compliance(
    site_id: uuid.UUID,
    body: ComplianceCheckRequest | None = None,
    db: AsyncSession = Depends(get_db),
    _site: Site = Depends(get_org_site),
) -> ComplianceCheckResponse:
    """Run compliance checks against a site's configuration."""
    ctx = await _build_site_context(site_id, db)
    frameworks = body.frameworks if body else None
    results = run_compliance_check(ctx, frameworks)
    overall_score = calculate_overall_score(results)

    return ComplianceCheckResponse(
        site_id=str(site_id),
        results=results,
        overall_score=overall_score,
    )


@router.get("/frameworks", response_model=list[dict])
async def list_frameworks() -> list[dict]:
    """List all available compliance frameworks."""
    return [
        {"id": fw.value, "name": fw.value.upper(), "description": desc}
        for fw, desc in [
            (Framework.GDPR, "EU General Data Protection Regulation"),
            (Framework.CNIL, "French Data Protection Authority (stricter GDPR)"),
            (Framework.CCPA, "California Consumer Privacy Act / CPRA"),
            (Framework.EPRIVACY, "EU ePrivacy Directive"),
            (Framework.LGPD, "Brazilian General Data Protection Law"),
        ]
    ]
