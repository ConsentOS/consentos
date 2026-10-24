"""Whether the banner is installed on a site, and what is wrong if not.

Two sources feed it:

* **Detection.** Each time the banner fetches its configuration, the page
  it is on is noted, as long as that page is on one of the site's
  domains. Recording is throttled through Redis to one write per site and
  host a minute, and happens after the response has been sent.
* **Checks.** "Check now" has the scanner load the site's home page and
  report what it finds, which is turned here into a list of checks, each
  with a plain-language fix when it fails.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config.settings import get_settings
from src.models.site import Site
from src.models.site_installation import SiteInstallation
from src.services.site_domains import host_matches_site, url_host

logger = logging.getLogger(__name__)

SEEN_THROTTLE_SECONDS = 60
_MAX_HOST_LENGTH = 253

# One client per event loop: a client's connections belong to the loop
# that opened them.
_redis_clients: dict[asyncio.AbstractEventLoop, Any] = {}


def _redis() -> Any:
    loop = asyncio.get_running_loop()
    if loop not in _redis_clients:
        import redis.asyncio as aioredis

        _redis_clients[loop] = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis_clients[loop]


def page_without_query(url: str) -> str:
    """The page address with its query string and fragment removed.

    Query strings can carry personal data, such as email addresses in
    campaign links, so they are never stored.
    """
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


async def _first_sighting_this_minute(site_id: uuid.UUID, host: str) -> bool:
    key = f"cmp:install:{site_id}:{host}"
    return bool(await _redis().set(key, "1", nx=True, ex=SEEN_THROTTLE_SECONDS))


async def record_banner_load(
    session_factory: async_sessionmaker[AsyncSession],
    site_id: uuid.UUID,
    source_url: str | None,
) -> None:
    """Note that the banner loaded on ``source_url``, if it is on the site.

    Runs as a background task after the configuration response, so it
    never fails or slows the banner: every error is logged and dropped.
    """
    host = url_host(source_url)
    if not source_url or not host or len(host) > _MAX_HOST_LENGTH:
        return
    try:
        if not await _first_sighting_this_minute(site_id, host):
            return
        async with session_factory() as db:
            site = await db.get(Site, site_id)
            if site is None or site.deleted_at is not None or not host_matches_site(host, site):
                return
            await mark_seen(db, site_id, page_without_query(source_url))
            await db.commit()
    except Exception:
        logger.warning("Could not record banner load for site %s", site_id, exc_info=True)


async def mark_seen(db: AsyncSession, site_id: uuid.UUID, page_url: str) -> None:
    """Record a sighting of the banner, keeping the first one."""
    now = datetime.now(UTC)
    stmt = insert(SiteInstallation).values(
        site_id=site_id, first_seen_at=now, last_seen_at=now, last_seen_url=page_url
    )
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=[SiteInstallation.site_id],
            set_={
                "first_seen_at": func.coalesce(
                    SiteInstallation.first_seen_at, stmt.excluded.first_seen_at
                ),
                "last_seen_at": stmt.excluded.last_seen_at,
                "last_seen_url": stmt.excluded.last_seen_url,
                "updated_at": now,
            },
        )
    )


async def get_installation(db: AsyncSession, site_id: uuid.UUID) -> SiteInstallation | None:
    return await db.get(SiteInstallation, site_id)


# ── State ────────────────────────────────────────────────────────────

InstallState = Literal["not_detected", "installed", "problem"]


def installation_state(installation: SiteInstallation | None) -> InstallState:
    """Summarise a site's installation for display.

    A failed check counts until the banner is seen again after it, since a
    later sighting shows the problem has been fixed.
    """
    if installation is None:
        return "not_detected"
    check = installation.last_check
    if check is not None and not check.get("ok", False):
        seen_since = (
            installation.last_seen_at is not None
            and installation.last_check_at is not None
            and installation.last_seen_at > installation.last_check_at
        )
        if not seen_since:
            return "problem"
    if installation.last_seen_at is not None or (check is not None and check.get("ok")):
        return "installed"
    return "not_detected"


# ── Checks ───────────────────────────────────────────────────────────

CheckStatus = Literal["passed", "failed", "skipped"]


def _check(
    key: str,
    label: str,
    status: CheckStatus,
    *,
    fix: str | None = None,
    detail: str | None = None,
    severity: Literal["error", "warning"] = "error",
) -> dict:
    return {
        "key": key,
        "label": label,
        "status": status,
        "severity": severity,
        "detail": detail,
        "fix": fix if status == "failed" else None,
    }


def _same_base(a: str | None, b: str | None) -> bool:
    return (a or "").strip().rstrip("/").lower() == (b or "").strip().rstrip("/").lower()


def diagnose(
    site: Site,
    found: dict,
    *,
    expected_api_base: str | None,
    checked_at: datetime,
) -> dict:
    """Turn what the scanner found on a page into checks with fixes.

    ``found`` is the scanner's ``/check-install`` response.
    ``expected_api_base`` is the deployment's public API address, or None
    when it isn't configured, in which case the address is judged by
    whether the banner could fetch its configuration.
    """
    checks: list[dict] = []
    skip = False

    def add(key: str, label: str, passed: bool | None, **kwargs: Any) -> None:
        if skip or passed is None:
            checks.append(_check(key, label, "skipped"))
        else:
            checks.append(_check(key, label, "passed" if passed else "failed", **kwargs))

    url = found.get("url", "")
    add(
        "reachable",
        "The page loads",
        bool(found.get("reachable")),
        detail=found.get("error"),
        fix=(
            f"We couldn't load {url}. Check the site is up and can be reached from the "
            "internet, then try again."
        ),
    )
    skip = not found.get("reachable")

    final_host = url_host(found.get("final_url") or url)
    add(
        "registered_domain",
        "The page is on one of this site's domains",
        host_matches_site(final_host, site),
        detail=final_host,
        fix=(
            f"The page is on {final_host}, which isn't one of this site's domains, so the "
            "banner won't run there. Add it to the site's domains, or check the site's "
            "domain is right."
        ),
    )

    loader = found.get("loader")
    config_requests = [r for r in found.get("config_requests", []) if r]
    # A tag manager can add the loader after the page loads, in which case
    # it isn't in the HTML but its configuration request is still seen.
    added_by_script = loader is None and bool(config_requests)
    add(
        "snippet_present",
        "The ConsentOS script is on the page",
        loader is not None or added_by_script,
        detail=(
            "Added by another script, such as a tag manager, rather than in the page's HTML."
            if added_by_script
            else None
        ),
        fix=(
            "We couldn't find consent-loader.js on the page. Add the install snippet to "
            "the page's <head>."
        ),
    )
    skip = skip or (loader is None and not added_by_script)

    if loader is not None:
        add(
            "site_id",
            "The script has this site's ID",
            loader.get("site_id") == str(site.id),
            detail=loader.get("site_id"),
            fix=(
                f'The script\'s data-site-id is "{loader.get("site_id") or ""}", not this '
                "site's ID. Copy the snippet again from this page."
            ),
        )
        api_base_ok = (
            None
            if expected_api_base is None
            else _same_base(loader.get("api_base"), expected_api_base)
        )
        add(
            "api_base",
            "The script points at this ConsentOS server",
            api_base_ok,
            detail=loader.get("api_base"),
            fix=(
                f'The script\'s data-api-base is "{loader.get("api_base") or ""}" but should '
                f'be "{expected_api_base}". Copy the snippet again from this page.'
            ),
        )
        add(
            "synchronous",
            "The script isn't loaded asynchronously",
            not (loader.get("is_async") or loader.get("is_defer")),
            fix=(
                "Remove async and defer from the script tag. Without them the page waits for "
                "the banner, so other scripts can't set cookies before it can stop them."
            ),
        )
        in_head = bool(loader.get("in_head"))
        add(
            "first_in_head",
            "The script is the first in <head>",
            in_head and bool(loader.get("first_script")),
            fix=(
                "Move the script above the other scripts in <head>, so it runs before them."
                if in_head
                else "Move the script into the page's <head>, above any other scripts."
            ),
        )
    else:
        for key, label in (
            ("site_id", "The script has this site's ID"),
            ("api_base", "The script points at this ConsentOS server"),
            ("synchronous", "The script isn't loaded asynchronously"),
            ("first_in_head", "The script is the first in <head>"),
        ):
            checks.append(_check(key, label, "skipped"))

    statuses = [r.get("status") for r in config_requests]
    reached = any(s in (200, 404) for s in statuses)
    add(
        "config_loaded",
        "The banner fetched its settings",
        reached,
        fix=(
            "The banner couldn't reach ConsentOS. Check the script's data-api-base, and that "
            "the site's content security policy allows requests to it."
            if config_requests
            else "The banner didn't ask for its settings. Check the snippet is complete and "
            "that nothing on the page, such as a content security policy, blocks it."
        ),
    )
    add(
        "banner_shown",
        "The banner appeared",
        bool(found.get("banner_rendered")),
        fix=(
            "The script loaded but the banner didn't appear. Check your browser's console on "
            "the site for errors."
        ),
    )

    skip = False
    add(
        "published",
        "This site's configuration is published",
        site.live_revision_id is not None,
        severity="warning",
        fix="Visitors see the built-in banner until you publish. Review and publish your changes.",
    )

    ok = not any(c["status"] == "failed" and c["severity"] == "error" for c in checks)
    return {"url": url, "checked_at": checked_at.isoformat(), "ok": ok, "checks": checks}


async def save_check(db: AsyncSession, site_id: uuid.UUID, result: dict, at: datetime) -> None:
    stmt = insert(SiteInstallation).values(site_id=site_id, last_check_at=at, last_check=result)
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=[SiteInstallation.site_id],
            set_={"last_check_at": at, "last_check": result, "updated_at": at},
        )
    )
