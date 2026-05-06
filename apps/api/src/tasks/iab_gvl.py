"""Daily IAB GVL refresh — Celery task.

Fetches the upstream Global Vendor List and upserts it into the local
cache (``iab_*`` tables). Scheduled daily by ``celery beat`` so the
admin UI's vendor pickers and the banner's vendor disclosure always
reflect a current view.

Failures are logged and re-raised so Celery's retry/failure handling
applies — the cache is not partially mutated on error because the
service layer wraps the upsert in a single transaction.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.celery_app import app

logger = logging.getLogger(__name__)


async def _run() -> dict[str, Any]:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from src.config.settings import get_settings
    from src.services.iab_gvl import refresh_gvl

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            result = await refresh_gvl(session, settings)
            return {
                "vendor_list_version": result.vendor_list_version,
                "vendors": result.vendors,
                "purposes": result.purposes,
            }
    finally:
        await engine.dispose()


@app.task(name="src.tasks.iab_gvl.refresh_gvl")
def refresh_gvl() -> dict[str, Any]:
    """Celery entry point for the daily GVL refresh."""
    return asyncio.run(_run())
