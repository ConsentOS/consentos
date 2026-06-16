"""Check whether a newer ConsentOS release is available.

Compares the running version (``settings.app_version``, injected at
build time) against the latest GitHub release. The latest version is
fetched once a day by ``src.tasks.update_check`` and cached in Redis;
this module reads that cache and does the comparison.

Every failure is swallowed: if the latest version can't be determined
the feature reports "no update" rather than erroring, so the admin UI
never breaks because GitHub is unreachable.
"""

from __future__ import annotations

import logging

import httpx

from src.config.settings import Settings

logger = logging.getLogger(__name__)

_CACHE_KEY = "consentos:latest_version"
# ~25h, so the value survives a single missed daily refresh.
_CACHE_TTL_SECONDS = 90_000


def _parse(version: str) -> tuple[int, int, int] | None:
    """Parse a semver string into a comparable tuple.

    Ignores a leading ``v`` and any pre-release / build suffix. Returns
    ``None`` for anything that isn't a release version (e.g. the
    ``0.0.0-dev`` sentinel parses, but a non-numeric tag does not), so
    callers treat it as "can't compare".
    """
    core = version.strip().lstrip("vV").split("-")[0].split("+")[0]
    parts = core.split(".")
    if len(parts) != 3:
        return None
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def is_newer(current: str, latest: str) -> bool:
    """True when ``latest`` is a strictly higher release than ``current``."""
    current_parsed = _parse(current)
    latest_parsed = _parse(latest)
    if current_parsed is None or latest_parsed is None:
        return False
    # The dev sentinel (0.0.0) is lower than any real release, which is
    # the behaviour we want: source builds never nag.
    return latest_parsed > current_parsed


async def fetch_latest_version(settings: Settings) -> str | None:
    """Fetch the latest release tag from GitHub, or ``None`` on failure.

    Returned with any leading ``v`` stripped (e.g. ``0.3.0``).
    """
    url = f"https://api.github.com/repos/{settings.update_check_repo}/releases/latest"
    try:
        async with httpx.AsyncClient(timeout=settings.update_check_timeout_seconds) as client:
            resp = await client.get(url, headers={"Accept": "application/vnd.github+json"})
        if resp.status_code != 200:
            logger.info("update check: GitHub returned HTTP %s", resp.status_code)
            return None
        tag = resp.json().get("tag_name")
        if isinstance(tag, str) and tag.strip():
            return tag.strip().lstrip("vV")
        return None
    except Exception as exc:
        logger.info("update check: could not fetch latest version: %s", exc)
        return None


def _redis(settings: Settings):
    import redis.asyncio as aioredis

    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def cache_latest_version(version: str, settings: Settings) -> None:
    """Store the latest known version in Redis with a daily TTL."""
    client = _redis(settings)
    try:
        await client.set(_CACHE_KEY, version, ex=_CACHE_TTL_SECONDS)
    finally:
        await client.aclose()


async def get_cached_latest_version(settings: Settings) -> str | None:
    """Read the cached latest version, or ``None`` if absent/unreachable."""
    client = _redis(settings)
    try:
        return await client.get(_CACHE_KEY)
    except Exception as exc:
        logger.info("update check: could not read cached version: %s", exc)
        return None
    finally:
        await client.aclose()


async def get_version_info(settings: Settings) -> dict:
    """Assemble the payload behind ``GET /api/v1/system/version``."""
    current = settings.app_version.strip().lstrip("vV")
    latest = await get_cached_latest_version(settings)
    return {
        "current": current,
        "latest": latest,
        "update_available": bool(latest) and is_newer(current, latest),
    }
