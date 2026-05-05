"""Anonymous telemetry — daily heartbeat with deployment metadata.

Collects bucketed scale metrics, feature toggles, and stack versions for
this ConsentOS deployment and POSTs them to the configured telemetry
endpoint. The full payload schema and operator-facing audit instructions
live in ``docs/telemetry.md``.

What is **never** collected:
- consent records, TC strings, cookie names or scan results
- site domains, organisation names, user emails or IDs
- IP addresses or any request-scoped data

What **is** collected:
- a stable anonymous instance UUID generated locally on first boot
- ConsentOS version, edition (CE/EE), Python version, deployment kind
- bucketed counts of orgs/sites/users/scans/consents
- feature flags (TCF, auto-blocking, GeoIP configured, etc.)
- Postgres major version

Privacy posture: every successful send writes the payload to the
application log at INFO so operators can audit exactly what left the
network. Disable entirely with ``TELEMETRY_ENABLED=false``.
"""

from __future__ import annotations

import logging
import os
import platform
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.edition import edition_name
from src.config.settings import Settings
from src.models.consent import ConsentRecord
from src.models.instance import Instance
from src.models.organisation import Organisation
from src.models.scan import ScanJob
from src.models.site import Site
from src.models.site_config import SiteConfig
from src.models.user import User

logger = logging.getLogger(__name__)

TELEMETRY_SCHEMA_VERSION = 1


def bucket(n: int) -> str:
    """Map a non-negative count to a privacy-preserving bucket label.

    Buckets are coarse enough that a self-hosted operator cannot be
    re-identified by exact scale. ``0`` is reported as-is so we can
    distinguish empty installs from buckets containing one entity.
    """
    if n <= 0:
        return "0"
    if n < 10:
        return "1-10"
    if n < 100:
        return "10-100"
    if n < 1_000:
        return "100-1k"
    if n < 10_000:
        return "1k-10k"
    return "10k+"


def detect_deployment() -> str:
    """Identify the deployment shape from a hint env var.

    Set ``CONSENTOS_DEPLOYMENT`` to ``docker-compose``, ``helm``,
    ``cloud-run``, etc. via the deployment manifests. Returns
    ``"unknown"`` when nothing is set.
    """
    return os.environ.get("CONSENTOS_DEPLOYMENT", "unknown")


async def get_or_create_instance(session: AsyncSession) -> Instance:
    """Return the singleton ``Instance`` row, creating it on first call."""
    existing = (await session.execute(select(Instance).limit(1))).scalar_one_or_none()
    if existing is not None:
        return existing

    instance = Instance()
    session.add(instance)
    await session.flush()
    return instance


async def _postgres_version(session: AsyncSession) -> str:
    """Return the Postgres major.minor version string, or ``"unknown"``."""
    try:
        raw = (await session.execute(select(func.version()))).scalar_one()
    except Exception:  # pragma: no cover - defensive, never block heartbeat
        return "unknown"
    # ``version()`` returns e.g. "PostgreSQL 16.2 (Debian 16.2-1.pgdg...)"
    parts = str(raw).split()
    return parts[1] if len(parts) >= 2 else "unknown"


async def _collect_counts(session: AsyncSession) -> dict[str, str]:
    """Return bucketed counts of the main scale-bearing entities."""
    since = datetime.now(UTC) - timedelta(hours=24)

    orgs = (await session.execute(select(func.count(Organisation.id)))).scalar_one()
    sites = (await session.execute(select(func.count(Site.id)))).scalar_one()
    users = (await session.execute(select(func.count(User.id)))).scalar_one()
    scans_24h = (
        await session.execute(
            select(func.count(ScanJob.id)).where(ScanJob.created_at >= since),
        )
    ).scalar_one()
    consents_24h = (
        await session.execute(
            select(func.count(ConsentRecord.id)).where(ConsentRecord.consented_at >= since),
        )
    ).scalar_one()

    return {
        "orgs": bucket(orgs),
        "sites": bucket(sites),
        "users": bucket(users),
        "scans_last_24h": bucket(scans_24h),
        "consents_last_24h": bucket(consents_24h),
    }


async def _collect_features(
    session: AsyncSession,
    settings: Settings,
) -> dict[str, Any]:
    """Return feature-usage signals — counts bucketed, toggles boolean."""
    tcf = (
        await session.execute(
            select(func.count(SiteConfig.id)).where(SiteConfig.tcf_enabled.is_(True)),
        )
    ).scalar_one()
    blocking = (
        await session.execute(
            select(func.count(SiteConfig.id)).where(SiteConfig.blocking_mode == "opt_in"),
        )
    ).scalar_one()
    scheduled = (
        await session.execute(
            select(func.count(SiteConfig.id)).where(SiteConfig.scan_schedule_cron.isnot(None)),
        )
    ).scalar_one()

    return {
        "tcf_v22_sites": bucket(tcf),
        "auto_blocking_sites": bucket(blocking),
        "scanner_scheduled_sites": bucket(scheduled),
        "geoip_header_configured": settings.geoip_country_header is not None,
        "geoip_maxmind_configured": settings.geoip_maxmind_db_path is not None,
        "rate_limit_enabled": settings.rate_limit_enabled,
        "compliance_ee": edition_name() == "ee",
    }


def build_payload(
    *,
    instance_id: str,
    settings: Settings,
    counts: dict[str, str],
    features: dict[str, Any],
    postgres_version: str,
) -> dict[str, Any]:
    """Assemble the heartbeat payload in stable schema order."""
    return {
        "telemetry_schema": TELEMETRY_SCHEMA_VERSION,
        "instance_id": instance_id,
        "sent_at": datetime.now(UTC).isoformat(),
        "version": settings.app_version,
        "edition": edition_name(),
        "python_version": platform.python_version(),
        "platform": sys.platform,
        "deployment": detect_deployment(),
        "counts": counts,
        "features": features,
        "stack": {
            "postgres_version": postgres_version,
            "redis_present": True,
        },
    }


async def collect_payload(session: AsyncSession, settings: Settings) -> dict[str, Any]:
    """Build a heartbeat payload from the live database."""
    instance = await get_or_create_instance(session)
    counts = await _collect_counts(session)
    features = await _collect_features(session, settings)
    pg_version = await _postgres_version(session)
    return build_payload(
        instance_id=str(instance.id),
        settings=settings,
        counts=counts,
        features=features,
        postgres_version=pg_version,
    )


async def send_heartbeat(session: AsyncSession, settings: Settings) -> dict[str, Any]:
    """Collect and POST the heartbeat. Logs the payload either way.

    Returns a small status dict for the Celery task to surface in the
    result backend. Network failures are logged and swallowed — telemetry
    must never break the worker.
    """
    if not settings.telemetry_active:
        logger.debug("telemetry.skipped", extra={"reason": "disabled"})
        return {"sent": False, "reason": "disabled"}

    payload = await collect_payload(session, settings)
    logger.info("telemetry.payload", extra={"payload": payload})

    try:
        async with httpx.AsyncClient(timeout=settings.telemetry_timeout_seconds) as client:
            response = await client.post(settings.telemetry_endpoint, json=payload)
            response.raise_for_status()
    except Exception as exc:
        logger.warning("telemetry.send_failed", extra={"error": str(exc)})
        return {"sent": False, "reason": "network_error"}

    instance = await get_or_create_instance(session)
    instance.last_telemetry_at = datetime.now(UTC)
    await session.commit()
    return {"sent": True, "instance_id": payload["instance_id"]}
