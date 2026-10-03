"""Dynamic CORS origin validation.

Registered site domains are allowed in addition to the static
allowed_origins list. The domain set is cached in Redis (shared across
workers) and invalidated on site mutations.
"""

from __future__ import annotations

import json
import logging
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.site import Site

logger = logging.getLogger(__name__)

_REDIS_KEY = "cmp:cors:allowed_domains"
_redis: object | None = None


def _get_redis() -> object | None:
    """Return the shared async Redis client, or None if Redis is unavailable."""
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis.asyncio as aioredis

        from src.config.settings import get_settings

        _redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        return _redis
    except Exception:
        logger.warning("CORS domain cache: Redis unavailable", exc_info=True)
        return None


def extract_domain_from_origin(origin: str) -> str | None:
    """Extract the hostname from an origin URL.

    e.g. 'https://example.com:443' → 'example.com'
    """
    try:
        parsed = urlparse(origin)
        return parsed.hostname
    except Exception:
        return None


async def get_allowed_domains(db: AsyncSession) -> set[str]:
    """Fetch all registered domains (primary + additional) from active sites."""
    result = await db.execute(
        select(Site.domain, Site.additional_domains).where(
            Site.is_active.is_(True),
            Site.deleted_at.is_(None),
        )
    )

    domains: set[str] = set()
    for row in result.all():
        domains.add(row.domain.lower())
        if row.additional_domains:
            for d in row.additional_domains:
                domains.add(d.lower())

    return domains


def is_origin_allowed(
    origin: str,
    static_origins: list[str],
    registered_domains: set[str],
) -> bool:
    """Check if an origin is allowed by either the static list or registered domains.

    Args:
        origin: The Origin header value (e.g. 'https://example.com').
        static_origins: Statically configured allowed origins from settings.
        registered_domains: Set of registered site domains from the database.

    Returns:
        True if the origin is allowed.
    """
    # Check static origins first (exact match)
    if origin in static_origins:
        return True

    # Wildcard — allow everything
    if "*" in static_origins:
        return True

    # Extract domain from origin and check against registered domains
    domain = extract_domain_from_origin(origin)
    return bool(domain and domain.lower() in registered_domains)


async def _fetch_allowed_domains() -> set[str]:
    """Read registered domains from the database (split out so tests can patch it)."""
    from src.db.session import async_session_factory

    async with async_session_factory() as db:
        return await get_allowed_domains(db)


async def get_allowed_domains_cached(ttl: int | None = None) -> set[str]:
    """Return registered site domains, cached in Redis (shared across workers)."""
    if ttl is None:
        from src.config.settings import get_settings

        ttl = get_settings().cors_cache_ttl

    redis = _get_redis()

    if redis is not None:
        try:
            cached = await redis.get(_REDIS_KEY)  # type: ignore[union-attr]
            if cached:
                return set(json.loads(cached))
        except Exception:
            logger.debug("Redis read failed for allowed domains", exc_info=True)

    try:
        domains = await _fetch_allowed_domains()
    except Exception:
        logger.warning(
            "Failed to fetch allowed domains from the database",
            exc_info=True,
        )
        return set()

    if redis is not None:
        try:
            await redis.set(  # type: ignore[union-attr]
                _REDIS_KEY,
                json.dumps(sorted(domains)),
                ex=ttl,
            )
        except Exception:
            logger.debug("Redis write failed for allowed domains", exc_info=True)

    return domains


async def invalidate_allowed_domains_cache() -> None:
    """Drop the shared allowed-domains cache (called after site mutations)."""
    redis = _get_redis()
    if redis is None:
        return
    try:
        await redis.delete(_REDIS_KEY)  # type: ignore[union-attr]
    except Exception:
        logger.debug("Redis delete failed for allowed domains", exc_info=True)
