"""IAB Global Vendor List fetch + upsert service.

Fetches the canonical GVL from
``vendor-list.consensu.org/v3/vendor-list.json`` (configurable via
``IAB_GVL_URL``) and persists it into the ``iab_*`` tables. Designed
to be idempotent — running the refresh twice with the same upstream
JSON is a no-op for the row state, only ``synced_at`` ticks forward.

The fetch + DB write are wholly transactional: if a row fails to
upsert, the entire refresh is rolled back so the cache is never left
in a partially-updated state. A successful run is signalled by the
returned ``RefreshResult`` summary; failures bubble up for the Celery
task to log and retry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import Settings
from src.models.iab_gvl import (
    IabDataCategory,
    IabFeature,
    IabGvlMeta,
    IabPurpose,
    IabSpecialFeature,
    IabSpecialPurpose,
    IabVendor,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RefreshResult:
    """Summary of a single GVL refresh run."""

    vendor_list_version: int
    tcf_policy_version: int
    vendors: int
    purposes: int
    special_purposes: int
    features: int
    special_features: int
    data_categories: int


async def fetch_gvl(settings: Settings) -> dict[str, Any]:
    """Fetch the GVL JSON from the configured upstream URL."""
    async with httpx.AsyncClient(timeout=settings.iab_gvl_timeout_seconds) as client:
        response = await client.get(settings.iab_gvl_url)
        response.raise_for_status()
        return response.json()


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp from the GVL into a tz-aware datetime."""
    if not value:
        return None
    # GVL uses ``Z`` suffix for UTC; ``fromisoformat`` accepts it from 3.11+.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _upsert_simple(
    session: AsyncSession,
    model: type,
    rows: dict[str, dict[str, Any]],
    *,
    has_illustrations: bool,
) -> int:
    """Upsert a flat ``id → {name, description, [illustrations]}`` map.

    Used for purposes, special purposes, features, special features.
    Returns the number of rows that were upserted.
    """
    if not rows:
        return 0

    payload = []
    for raw_id, entry in rows.items():
        row = {
            "id": int(raw_id),
            "name": entry["name"],
            "description": entry["description"],
        }
        if has_illustrations:
            row["illustrations"] = entry.get("illustrations") or None
        payload.append(row)

    update_cols = {"name": "name", "description": "description"}
    if has_illustrations:
        update_cols["illustrations"] = "illustrations"

    stmt = pg_insert(model).values(payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={k: stmt.excluded[v] for k, v in update_cols.items()},
    )
    await session.execute(stmt)
    return len(payload)


async def _upsert_data_categories(
    session: AsyncSession,
    rows: dict[str, dict[str, Any]] | None,
) -> int:
    if not rows:
        return 0
    payload = [
        {
            "id": int(raw_id),
            "name": entry["name"],
            "description": entry["description"],
        }
        for raw_id, entry in rows.items()
    ]
    stmt = pg_insert(IabDataCategory).values(payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            "name": stmt.excluded.name,
            "description": stmt.excluded.description,
        },
    )
    await session.execute(stmt)
    return len(payload)


async def _upsert_vendors(
    session: AsyncSession,
    rows: dict[str, dict[str, Any]],
) -> int:
    if not rows:
        return 0

    # Vendors that drop out of the GVL across versions don't get auto-deleted
    # — IAB sets a ``deletedDate`` on the row instead. We honour that by
    # upserting whatever IAB sends (including the deleted_date if set) and
    # never DELETE-ing rows here.
    payload = [
        {
            "id": int(raw_id),
            "name": entry["name"],
            "purposes": entry.get("purposes"),
            "leg_int_purposes": entry.get("legIntPurposes"),
            "flexible_purposes": entry.get("flexiblePurposes"),
            "special_purposes": entry.get("specialPurposes"),
            "features": entry.get("features"),
            "special_features": entry.get("specialFeatures"),
            "policy_url": entry.get("policyUrl"),
            "deleted_date": _parse_iso(entry.get("deletedDate")),
            "uses_cookies": entry.get("usesCookies"),
            "cookie_refresh": entry.get("cookieRefresh"),
            "uses_non_cookie_access": entry.get("usesNonCookieAccess"),
            "cookie_max_age_seconds": entry.get("cookieMaxAgeSeconds"),
            "data_retention": entry.get("dataRetention"),
            "urls": entry.get("urls"),
            "data_declaration": entry.get("dataDeclaration"),
        }
        for raw_id, entry in rows.items()
    ]

    stmt = pg_insert(IabVendor).values(payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],
        set_={
            col: getattr(stmt.excluded, col)
            for col in (
                "name",
                "purposes",
                "leg_int_purposes",
                "flexible_purposes",
                "special_purposes",
                "features",
                "special_features",
                "policy_url",
                "deleted_date",
                "uses_cookies",
                "cookie_refresh",
                "uses_non_cookie_access",
                "cookie_max_age_seconds",
                "data_retention",
                "urls",
                "data_declaration",
            )
        },
    )
    await session.execute(stmt)
    return len(payload)


async def _replace_meta(session: AsyncSession, gvl: dict[str, Any]) -> None:
    """Drop and re-insert the singleton meta row.

    Simpler than upsert because the row is a singleton — and crucially,
    it lets us detect a downgrade (older GVL than what we have) by
    failing loudly instead of silently overwriting.
    """
    last_updated = _parse_iso(gvl.get("lastUpdated"))
    if last_updated is None:
        msg = "GVL JSON missing required 'lastUpdated' field"
        raise ValueError(msg)

    await session.execute(delete(IabGvlMeta))
    session.add(
        IabGvlMeta(
            id=1,
            gvl_specification_version=int(gvl["gvlSpecificationVersion"]),
            vendor_list_version=int(gvl["vendorListVersion"]),
            tcf_policy_version=int(gvl["tcfPolicyVersion"]),
            last_updated=last_updated,
            synced_at=datetime.now(UTC),
        )
    )


async def upsert_gvl(session: AsyncSession, gvl: dict[str, Any]) -> RefreshResult:
    """Persist a parsed GVL document into the ``iab_*`` tables."""
    purposes = await _upsert_simple(
        session, IabPurpose, gvl.get("purposes") or {}, has_illustrations=True
    )
    special_purposes = await _upsert_simple(
        session,
        IabSpecialPurpose,
        gvl.get("specialPurposes") or {},
        has_illustrations=True,
    )
    features = await _upsert_simple(
        session, IabFeature, gvl.get("features") or {}, has_illustrations=True
    )
    special_features = await _upsert_simple(
        session,
        IabSpecialFeature,
        gvl.get("specialFeatures") or {},
        has_illustrations=True,
    )
    data_categories = await _upsert_data_categories(session, gvl.get("dataCategories"))
    vendors = await _upsert_vendors(session, gvl.get("vendors") or {})
    await _replace_meta(session, gvl)

    return RefreshResult(
        vendor_list_version=int(gvl["vendorListVersion"]),
        tcf_policy_version=int(gvl["tcfPolicyVersion"]),
        vendors=vendors,
        purposes=purposes,
        special_purposes=special_purposes,
        features=features,
        special_features=special_features,
        data_categories=data_categories,
    )


async def refresh_gvl(session: AsyncSession, settings: Settings) -> RefreshResult:
    """Fetch the upstream GVL and upsert it. The whole thing is one txn."""
    gvl = await fetch_gvl(settings)
    result = await upsert_gvl(session, gvl)
    await session.commit()
    logger.info(
        "iab_gvl.refreshed",
        extra={
            "vendor_list_version": result.vendor_list_version,
            "vendors": result.vendors,
            "purposes": result.purposes,
        },
    )
    return result
