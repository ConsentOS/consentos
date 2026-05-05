"""Anonymous telemetry heartbeat — Celery task.

Schedules via ``celery beat`` once per day. The actual collection and
send logic lives in ``src.services.telemetry``; this module only wraps
it in the Celery entry point and runs the async work in a fresh event
loop with a dedicated SQLAlchemy session.

See ``docs/telemetry.md`` for what is sent and how to opt out.
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
    from src.services.telemetry import send_heartbeat

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            return await send_heartbeat(session, settings)
    finally:
        await engine.dispose()


@app.task(name="src.tasks.telemetry.send_heartbeat")
def send_heartbeat() -> dict[str, Any]:
    """Celery entry point for the daily telemetry heartbeat."""
    return asyncio.run(_run())
