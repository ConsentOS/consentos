"""Daily update check — Celery task.

Fetches the latest ConsentOS release version from GitHub and caches it
in Redis for ``src.services.update_check`` to read. Scheduled daily by
``celery beat``.

Unlike most tasks this never raises: a failed or rate-limited fetch
leaves the previously cached value untouched and the admin UI simply
shows no update, per the feature's "no response → do nothing" rule.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.celery_app import app

logger = logging.getLogger(__name__)


async def _run() -> dict[str, Any]:
    from src.config.settings import get_settings
    from src.services.update_check import cache_latest_version, fetch_latest_version

    settings = get_settings()
    latest = await fetch_latest_version(settings)
    if latest:
        await cache_latest_version(latest, settings)
    return {"latest": latest}


@app.task(name="src.tasks.update_check.refresh_latest_version")
def refresh_latest_version() -> dict[str, Any]:
    """Celery entry point for the daily update check."""
    return asyncio.run(_run())
